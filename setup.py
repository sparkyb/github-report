import os.path

import setuptools


# read the contents of the README.md file
setup_dir = os.path.abspath(os.path.dirname(__file__))
readme_file = os.path.join(setup_dir, 'README.md')
with open(readme_file, encoding='utf-8') as fp:
  long_description = fp.read()


setuptools.setup(
    name='github-report',
    version='0.1',
    description='Generates a report of metadata about repositories for a '
        'GitHub user or organization',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/sparkyb/github-report',
    author='Ben Buchwald',
    author_email='ben@ngcreative.com',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: Microsoft :: Windows',
        'Operating System :: POSIX :: Linux',
        'Operating System :: MacOS :: MacOS X',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Topic :: Software Development :: Version Control :: Git',
    ],
    packages=setuptools.find_packages(),
    install_requires=[
        'gitpython',
        'humanize',
        'python-dateutil',
        'requests',
        'tabulate',
    ],
    python_requires='>=3.6',
    entry_points={
        'console_scripts': [
            'github-report = github_report:main',
        ],
    },
)
