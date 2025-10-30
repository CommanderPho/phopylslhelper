# LSL Stream Tools - Technical Design

## Context
Need to implement flexible LSL stream visualization and cloud relay while preserving timestamp synchronization. Target users are neuroscience researchers requiring real-time data processing and remote analysis capabilities.

**Constraints:**
- Must maintain sub-100ms latency for visualization
- Cannot lose LSL timestamp precision in cloud transmission
- Must work across Windows, Linux, macOS
- Should handle multiple concurrent streams
- Memory usage must be bounded for continuous operation

## Goals / Non-Goals

**Goals:**
- ✅ Support multiple visualization backends (MNE-LSL, PyQt5, web)
- ✅ Preserve LSL timestamp synchronization in cloud streaming
- ✅ Plugin architecture for extensibility
- ✅ Configuration-driven setup
- ✅ Comprehensive error handling and recovery

**Non-Goals:**
- ❌ Real-time signal processing algorithms (focus on display/streaming)
- ❌ LSL stream generation (only consumption)
- ❌ Custom machine learning pipelines
- ❌ Mobile app development

## Decisions

### 1. Multi-Backend Visualization Architecture
**Decision:** Implement abstract base class with concrete backends for different visualization needs.

**Rationale:**
- MNE-LSL for advanced neuroscience features
- PyQt5 for lightweight custom displays  
- Web backend for remote access
- Allows users to choose optimal tool for their use case

### 2. MQTT + JSON for Cloud Streaming
**Decision:** Use MQTT message broker with JSON payloads containing LSL data + metadata.

**Rationale:**
- MQTT provides reliable pub/sub messaging
- JSON preserves timestamp precision as strings
- Industry standard for IoT/streaming applications
- Easy integration with cloud services

### 3. Timestamp Preservation Strategy
**Decision:** Embed LSL timestamps and clock sync metadata in message payload.

**Structure:**
```json
{
  "stream_id": "EEG_stream_1",
  "lsl_timestamp": "1703025600.123456789",
  "clock_offset": "0.000123",
  "sample_data": [1.2, 3.4, 5.6],
  "transmission_time": "2024-12-20T10:00:00.123Z"
}
```

## Migration Plan
1. **Phase 1:** Core LSL stream management
2. **Phase 2:** Basic visualization backend
3. **Phase 3:** Cloud streaming infrastructure  
4. **Phase 4:** Advanced features and optimization

## Open Questions
- Which cloud message brokers to support initially?
- Performance requirements for simultaneous stream count?
- Security requirements for cloud transmission?


