from setuptools import (setup, find_packages)


with open("README.md", "r") as f:
    long_description = f.read()


setup(name="qclipx",
      version="1.0.0",
      author="Weitian Leung",
      author_email="weitianleung@gmail.com",
      description='Cross platform clipboard tool',
      long_description_content_type="text/markdown",
      long_description=long_description,
      keywords="clipboard tool viewer",
      url="https://github.com/timxx/qclipx",
      packages=find_packages(),
      license="MIT",
      python_requires='>=3.0',
      entry_points={
          "console_scripts": [
              "qclipx=qclipx.qclipx:main",
          ]
      },
      install_requires=["PySide2", "pyhexedit"],
      classifiers=[
          "License :: OSI Approved :: MIT License",
          "Operating System :: POSIX",
          "Operating System :: POSIX :: BSD",
          "Operating System :: POSIX :: Linux",
          "Operating System :: Microsoft :: Windows",
          "Programming Language :: Python :: 3",
      ])
