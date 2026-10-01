import time
try:
    data = bytearray(512 * 1024 * 1024)
    time.sleep(2)
    print('ALLOCATED_SUCCESSFULLY')
except MemoryError:
    print('PYTHON_MEMORY_ERROR')
