import redis
kw = dict(host='127.0.0.1', port=6379, db=0, decode_responses=True, socket_timeout=1, socket_connect_timeout=2)
print('redis module:', getattr(redis, '__version__', 'unknown'))
try:
    redis.StrictRedis(**kw, encoding='utf-8')
    print('encoding ok')
except Exception as e:
    print('encoding failed:', type(e), e)
try:
    redis.StrictRedis(**kw, charset='utf-8')
    print('charset ok')
except Exception as e:
    print('charset failed:', type(e), e)
try:
    redis.StrictRedis(**kw)
    print('no extra ok')
except Exception as e:
    print('no extra failed:', type(e), e)
