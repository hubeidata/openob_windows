import sys, sysconfig
print(sys.version)
print('SO:', sysconfig.get_config_var('SO'))
print('purelib:', sysconfig.get_paths()['purelib'])