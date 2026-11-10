import socket
import select
import time
import logging

logger = logging.getLogger("openflight.udp_transport")

class UDPSerial:
    """Acts exactly like a PySerial object, but reads from a UDP stream buffer."""
    is_open = True
    
    def __init__(self, port_uri, timeout_val):
        self.timeout = timeout_val
        self.rx_buffer = bytearray()
        
        self.internal_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_port = int(port_uri.replace("udp://", ""))
        self.internal_sock.bind(("0.0.0.0", udp_port))
        logger.info("[UDP Transport] Listening on port %s", udp_port)

    def _pump_socket(self):
        """Drain all waiting UDP packets into the flat stream buffer."""
        while True:
            ready, _, _ = select.select([self.internal_sock], [], [], 0.0)
            if ready:
                try:
                    data, addr = self.internal_sock.recvfrom(65536)
                    if data:
                        self.rx_buffer.extend(data)
                        self.last_client = addr  # Save the sender's IP and port!
                except Exception:
                    break
            else:
                break

    @property
    def in_waiting(self):
        self._pump_socket()
        return len(self.rx_buffer)

    def read(self, size=4096):
        if not self.rx_buffer:
            ready, _, _ = select.select([self.internal_sock], [], [], self.timeout)
            if ready:
                self._pump_socket()
                
        if not self.rx_buffer:
            return b""
            
        chunk = self.rx_buffer[:size]
        self.rx_buffer = self.rx_buffer[size:]
        return bytes(chunk)

    def readline(self):
        start = time.time()
        while b'\n' not in self.rx_buffer:
            ready, _, _ = select.select([self.internal_sock], [], [], 0.1)
            if ready:
                self._pump_socket()
            if self.timeout is not None and (time.time() - start) > self.timeout:
                break
                
        if b'\n' in self.rx_buffer:
            idx = self.rx_buffer.index(b'\n') + 1
            line = self.rx_buffer[:idx]
            self.rx_buffer = self.rx_buffer[idx:]
            return bytes(line)
        else:
            line = self.rx_buffer[:]
            self.rx_buffer.clear()
            return bytes(line)

    def write(self, data):
        """Forward OpenFlight's commands back to the ESP32/Simulator."""
        if hasattr(self, 'last_client') and self.last_client:
            try:
                self.internal_sock.sendto(data, self.last_client)
            except Exception:
                pass
        return len(data)
        
    def flush(self): pass
    def reset_input_buffer(self): self.rx_buffer.clear()
    def close(self): self.internal_sock.close()


class UDPInterceptorSocket:
    """Dummy socket that fools hardware triggers into reading from the stream buffer."""
    def __init__(self, udp_serial):
        self.udp_serial = udp_serial
        
    def recvfrom(self, size):
        return self.udp_serial.read(size), ("127.0.0.1", 12345)


def create_udp_transport(port_uri, timeout):
    """Factory method to generate the serial interface and the dummy socket."""
    serial_interface = UDPSerial(port_uri, timeout)
    dummy_socket = UDPInterceptorSocket(serial_interface)
    return serial_interface, dummy_socket