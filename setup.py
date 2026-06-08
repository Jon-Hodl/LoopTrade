from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="looptrade",
    version="1.0.0",
    author="Jon Hodl",
    author_email="jon@example.com",
    description="Automated Bitcoin grid trading bot for LN Markets",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Jon-Hodl/LoopTrade",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Financial and Insurance Industry",
        "Topic :: Office/Business :: Financial :: Investment",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
    ],
    python_requires=">=3.12",
    install_requires=[
        "flask>=2.0.0",
        "aiohttp>=3.8.0",
        "lnmarkets-sdk",
    ],
    dependency_links=[
        "git+https://github.com/ln-markets/sdk-python.git#egg=lnmarkets-sdk",
    ],
    entry_points={
        'console_scripts': [
            'looptrade=looptrade:main',
        ],
    },
    include_package_data=True,
    package_data={
        '': ['templates/*.html', 'static/*'],
    },
)
