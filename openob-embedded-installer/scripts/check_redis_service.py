import sys
try:
    from ui.services.redis_service import RedisService
except ModuleNotFoundError:
    # When running against the installed runtime, add the installed ui folder to sys.path
    sys.path.insert(0, r'C:\temp\openob_test_inst')
    from ui.services.redis_service import RedisService

s = RedisService()
print('HAS_REDIS', s.is_available)
print('connect result', s.connect('127.0.0.1', 6379))
