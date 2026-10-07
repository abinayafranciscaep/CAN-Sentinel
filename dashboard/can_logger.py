import can

bus = can.Bus(channel="vcan0", interface="socketcan")

try:
    while True:
        msg = bus.recv(timeout=1.0)
        if msg is None:
            continue

        timestamp = f"{msg.timestamp:.6f}"
        can_id = f"0x{msg.arbitration_id:03X}"
        dlc = msg.dlc
        data_hex = msg.data.hex().upper()
        label = "normal"

        print(f"{timestamp},{can_id},{dlc},{data_hex},{label}")
except KeyboardInterrupt:
    pass
finally:
    bus.shutdown()
