# Copyright (C) 2015 Bitquant Research Laboratories (Asia) Limited
# Released under the Simplified BSD License

from setuptools import (
    setup,
)

setup(
    name='cryptocurrency-price-api',
    version='0.5',
    author='Anil Daoud',
    author_email='anil+git@via.ecp.fr',
    url='https://github.com/AnilDaoud/cryptocurrency-price-api',
    description="API's for cryptocurrencies exchanges",
    long_description='''Price API's for cryptycurrencies exchanges''',
    license='MIT',
    packages=['exchanges'],
    install_requires=['requests', 'python-dateutil', 'websocket-client', 'configparser'],
    include_package_data=True,
    use_2to3=True
)
