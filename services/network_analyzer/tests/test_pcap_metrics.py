from pathlib import Path

import dpkt
import pytest

from pcap.analyzer import PcapAnalyzer
from tests.builders import (
    CLIENT_IP,
    CLIENT_PORT,
    SERVER_IP,
    SERVER_PORT,
    arp_packet,
    handshake_packets,
    tcp_packet,
    udp_packet,
    write_pcap,
)


def test_seven_metrics_from_controlled_tcp_capture(tmp_path: Path) -> None:
    packets = handshake_packets()
    packets += [
        (1.2, tcp_packet(CLIENT_IP, SERVER_IP, CLIENT_PORT, SERVER_PORT,
                         flags=dpkt.tcp.TH_ACK, sequence_number=101, payload=b"x" * 100)),
        (1.3, tcp_packet(SERVER_IP, CLIENT_IP, SERVER_PORT, CLIENT_PORT,
                         flags=dpkt.tcp.TH_ACK, window_size=0)),
        (1.4, tcp_packet(SERVER_IP, CLIENT_IP, SERVER_PORT, CLIENT_PORT,
                         flags=dpkt.tcp.TH_RST | dpkt.tcp.TH_ACK)),
        (1.5, arp_packet()),
    ]
    path = tmp_path / "controlled.pcap"
    write_pcap(path, packets)

    metrics = PcapAnalyzer().analyze(path)

    total = sum(len(packet) for _, packet in packets)
    assert metrics.handshake_rtt_avg == pytest.approx(0.05)
    assert metrics.retransmission_count == 1
    assert metrics.zero_window_event_count == 1
    assert metrics.tcp_reset_drops == 1
    assert metrics.total_transferred_bytes == total
    assert metrics.total_payload_bytes == 200
    assert metrics.overhead_ratio == pytest.approx((total - 200) / total)
    assert metrics.dominant_server_port == 443


def test_pcapdroid_raw_ip_and_udp(tmp_path: Path) -> None:
    packets = [(1.0, udp_packet(CLIENT_IP, SERVER_IP, CLIENT_PORT, SERVER_PORT, b"abc")[14:])]
    path = tmp_path / "phone.pcap"
    write_pcap(path, packets, linktype=101)

    metrics = PcapAnalyzer().analyze(path)

    assert metrics.total_transferred_bytes == len(packets[0][1])
    assert metrics.total_payload_bytes == 3
    assert metrics.handshake_rtt_avg is None
