from configs import WELL_KNOWN_PORTS
from metrics.models import PcapMetrics
from pcap.models import FlowKey, FlowRecord, ParsedCapture


class PcapMetricsAggregator:
    """Reduces a parsed capture's flows into the aggregate metrics stored in the network_metrics table."""

    def aggregate(self, capture: ParsedCapture) -> PcapMetrics:
        handshakes = [flow.handshake_rtt for flow in capture.flows if flow.handshake_rtt is not None]
        total_bytes = capture.other_frame_bytes + sum(flow.total_frame_bytes for flow in capture.flows)
        payload_bytes = sum(flow.payload_bytes for flow in capture.flows)
        port_bytes: dict[int, int] = {}
        for flow in capture.flows:
            endpoints = flow.flow_key
            candidates = [port for port in (endpoints.first_endpoint.port, endpoints.second_endpoint.port)
                          if port in WELL_KNOWN_PORTS]
            if candidates:
                port = min(candidates)
                port_bytes[port] = port_bytes.get(port, 0) + flow.total_frame_bytes
        dominant_port = max(port_bytes, key=port_bytes.get) if port_bytes else None
        return PcapMetrics(
            handshake_rtt_avg=sum(handshakes) / len(handshakes) if handshakes else None,
            retransmission_count=sum(flow.retransmission_count for flow in capture.flows),
            zero_window_event_count=sum(flow.zero_window_event_count for flow in capture.flows),
            tcp_reset_drops=sum(flow.reset_count for flow in capture.flows),
            total_transferred_bytes=total_bytes,
            total_payload_bytes=payload_bytes,
            overhead_ratio=(total_bytes - payload_bytes) / total_bytes if total_bytes else None,
            dominant_server_port=dominant_port,
        )


