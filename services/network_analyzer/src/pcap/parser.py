import enum
from bisect import bisect_left
import socket
import struct
from pathlib import Path
from typing import BinaryIO

import dpkt
from pcap.errors import PcapParseError
from pcap.models import FlowKey, FlowRecord, ParsedCapture

from utils.logging_setup import get_logger

logger = get_logger(__name__)


class DatalinkType(enum.IntEnum):
    """DLT (datalink type) stored in the libpcap file header: it says what precedes the IP packet in each record.

    ETHERNET (1): a 14-byte Ethernet header precedes the IP packet — captures made on a physical network card.
    RAW_IP (101): the IP packet starts at byte zero — captures made on tun/VPN interfaces. The pcap file
        format always stores 101 for raw IP; 12/14 are BSD-era values that never appear in capture files.
    LINUX_SLL (113): a 16-byte Linux cooked header precedes the IP packet — captures made with `tcpdump -i any`.
    """

    ETHERNET = 1
    RAW_IP = 101
    LINUX_SLL = 113


class _FlowAccumulator:
    """Mutable per-flow bookkeeping the parser folds into one FlowRecord: byte counters plus the TCP-only
    retransmission, zero-window and handshake state."""

    def __init__(self, flow_key: FlowKey) -> None:
        """Start with empty counters, no recorded handshake and no sent byte ranges."""
        self.flow_key = flow_key
        self.total_frame_bytes = 0
        self.payload_bytes = 0
        self.retransmission_count = 0
        self.zero_window_event_count = 0
        self.reset_count = 0
        self.handshake_rtt: float | None = None
        self._syn_timestamp: float | None = None
        self._syn_source: str | None = None
        self._syn_sequence: int | None = None
        self._sent_ranges: dict[str, list[tuple[int, int]]] = {}

    def add_tcp_segment(self, timestamp: float, segment: dpkt.tcp.TCP, frame_length: int, source_ip: str) -> None:
        self.total_frame_bytes += frame_length
        payload_length = len(segment.data)
        self.payload_bytes += payload_length
        if segment.flags & dpkt.tcp.TH_RST:
            self.reset_count += 1
        if segment.win == 0 and segment.flags & dpkt.tcp.TH_ACK:
            self.zero_window_event_count += 1

        sender = f"{source_ip}:{segment.sport}"
        if segment.flags & dpkt.tcp.TH_SYN and not segment.flags & dpkt.tcp.TH_ACK:
            if self._syn_timestamp is None:
                self._syn_timestamp = timestamp
                self._syn_source = sender
                self._syn_sequence = segment.seq
        elif segment.flags & dpkt.tcp.TH_SYN and segment.flags & dpkt.tcp.TH_ACK:
            if (self.handshake_rtt is None and self._syn_timestamp is not None
                    and sender != self._syn_source
                    and segment.ack == (self._syn_sequence + 1) % (1 << 32)):
                self.handshake_rtt = timestamp - self._syn_timestamp

        if payload_length:
            start, end = segment.seq, segment.seq + payload_length
            ranges = self._sent_ranges.setdefault(sender, [])
            index = bisect_left(ranges, (start, end))
            retransmitted = False
            if index and ranges[index - 1][1] > start:
                index -= 1
                retransmitted = True
            while index < len(ranges) and ranges[index][0] < end:
                old_start, old_end = ranges.pop(index)
                start, end = min(start, old_start), max(end, old_end)
                retransmitted = True
            if retransmitted:
                self.retransmission_count += 1
            ranges.insert(index, (start, end))

    def add_udp_datagram(self, datagram: dpkt.udp.UDP, frame_length: int) -> None:
        self.total_frame_bytes += frame_length
        self.payload_bytes += len(datagram.data)

    def record(self) -> FlowRecord:
        """Freeze the bookkeeping into the flow's immutable record."""
        return FlowRecord(
            flow_key=self.flow_key,
            total_frame_bytes=self.total_frame_bytes,
            payload_bytes=self.payload_bytes,
            retransmission_count=self.retransmission_count,
            zero_window_event_count=self.zero_window_event_count,
            reset_count=self.reset_count,
            handshake_rtt=self.handshake_rtt,
        )




class PcapParser:
    """Parses pcap/pcapng captures into per-flow records using dpkt (no external tools)."""

    DISSECTION_ERRORS: tuple[type[Exception], ...] = (dpkt.UnpackError, struct.error, IndexError)

    def parse(self, pcap_path: Path) -> ParsedCapture:
        """Dissect a capture into one record per TCP/UDP flow, plus the non-flow byte total.

        Flows are keyed by their canonical five-tuple, so both directions of a flow and both
        protocols on the same four-tuple are handled. Non-flow traffic (ARP, ICMP, ...) only
        counts its frame bytes. Individually malformed packets are skipped and counted; an
        unreadable file raises PcapParseError.
        """
        try:
            capture = self._parse(pcap_path)
        except OSError as error:
            raise PcapParseError(f"cannot read {pcap_path}: {error}") from error
        if capture.malformed_packet_count:
            logger.warning("%s: skipped %d malformed packet(s).", pcap_path.name, capture.malformed_packet_count)
        return capture

    def _parse(self, pcap_path: Path) -> ParsedCapture:
        flows: dict[FlowKey, _FlowAccumulator] = {}
        other_frame_bytes = 0
        malformed_packet_count = 0
        with pcap_path.open("rb") as handle:
            magic = handle.read(4)
            handle.seek(0)
            if magic == b"\x0a\x0d\x0d\x0a":
                reader = dpkt.pcapng.Reader(handle)
            elif magic in (b"\xd4\xc3\xb2\xa1", b"\xa1\xb2\xc3\xd4",
                           b"\x4d\x3c\xb2\xa1", b"\xa1\xb2\x3c\x4d"):
                reader = dpkt.pcap.Reader(handle)
                self._validate_classic_pcap(pcap_path)
            else:
                raise PcapParseError(f"unsupported or invalid pcap header: {pcap_path}")

            linktype = reader.datalink()
            if linktype not in DatalinkType:
                raise PcapParseError(f"unsupported datalink type {linktype}: {pcap_path}")
            try:
                for timestamp, frame in reader:
                    try:
                        packet = self._ip_packet(frame, linktype)
                        if packet is None:
                            other_frame_bytes += len(frame)
                            continue
                        if isinstance(packet, dpkt.ip.IP):
                            source_ip = socket.inet_ntop(socket.AF_INET, packet.src)
                            destination_ip = socket.inet_ntop(socket.AF_INET, packet.dst)
                        else:
                            source_ip = socket.inet_ntop(socket.AF_INET6, packet.src)
                            destination_ip = socket.inet_ntop(socket.AF_INET6, packet.dst)
                        transport = packet.data
                        if isinstance(transport, dpkt.tcp.TCP):
                            protocol = "TCP"
                        elif isinstance(transport, dpkt.udp.UDP):
                            protocol = "UDP"
                        else:
                            other_frame_bytes += len(frame)
                            continue
                        key = FlowKey.from_packet(
                            protocol, source_ip, transport.sport, destination_ip, transport.dport
                        )
                        flow = flows.setdefault(key, _FlowAccumulator(key))
                        if protocol == "TCP":
                            flow.add_tcp_segment(timestamp, transport, len(frame), source_ip)
                        else:
                            flow.add_udp_datagram(transport, len(frame))
                    except self.DISSECTION_ERRORS:
                        malformed_packet_count += 1
            except (dpkt.UnpackError, struct.error, ValueError) as error:
                raise PcapParseError(f"invalid capture {pcap_path}: {error}") from error
        return ParsedCapture(tuple(flow.record() for flow in flows.values()), other_frame_bytes, malformed_packet_count)

    @staticmethod
    def _ip_packet(frame: bytes, linktype: int) -> dpkt.ip.IP | dpkt.ip6.IP6 | None:
        if linktype == DatalinkType.ETHERNET:
            network = dpkt.ethernet.Ethernet(frame).data
        elif linktype == DatalinkType.LINUX_SLL:
            network = dpkt.sll.SLL(frame).data
        else:
            version = frame[0] >> 4
            if version == 4:
                network = dpkt.ip.IP(frame)
            elif version == 6:
                network = dpkt.ip6.IP6(frame)
            else:
                return None
        return network if isinstance(network, (dpkt.ip.IP, dpkt.ip6.IP6)) else None

    @staticmethod
    def _validate_classic_pcap(path: Path) -> None:
        """Reject truncated records that dpkt's iterator otherwise silently ignores."""
        with path.open("rb") as handle:
            magic = handle.read(4)
            endian = "<" if magic in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1") else ">"
            if len(handle.read(20)) != 20:
                raise PcapParseError(f"truncated pcap header: {path}")
            while header := handle.read(16):
                if len(header) != 16:
                    raise PcapParseError(f"truncated packet header: {path}")
                captured_length = struct.unpack(endian + "IIII", header)[2]
                if len(handle.read(captured_length)) != captured_length:
                    raise PcapParseError(f"truncated packet data: {path}")
