import time

def build_heartbeat(node, seq):
    return {
        "node": node,
        "seq": seq,
        "timestamp": time.time(),
    }