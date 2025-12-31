from redis import Redis
import sys
try:
    Redis(host='127.0.0.1', port=6379, encoding='utf-8')
    print('constructed ok')
    sys.exit(0)
except TypeError as e:
    print('TypeError', e)
    sys.exit(2)
except Exception as e:
    print('Other', e)
    sys.exit(3)
