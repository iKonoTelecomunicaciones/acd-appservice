import setuptools

from acd_appservice.get_version import git_revision, git_tag, linkified_version, version

try:
    long_desc = open("README.md").read()
except IOError:
    long_desc = "Failed to read README.md"

with open("requirements.txt") as reqs:
    install_requires = reqs.read().splitlines()

with open("requirements-dev.txt") as reqs:
    extras_require = {}
    current = []
    for line in reqs.read().splitlines():
        if line.startswith("#/"):
            extras_require[line[2:]] = current = []
        elif not line or line.startswith("#"):
            continue
        else:
            current.append(line)

extras_require["all"] = list({dep for deps in extras_require.values() for dep in deps})


with open("acd_appservice/version.py", "w") as version_file:
    version_file.write(
        f"""# Generated in setup.py

git_tag = {git_tag!r}
git_revision = {git_revision!r}
version = {version!r}
linkified_version = {linkified_version!r}
"""
    )

setuptools.setup(
    name="acd-appservice",
    version=version,
    url="https://gitlab.com/iKono/acd-appservice",
    project_urls={
        "Changelog": "https://gitlab.com/iKono/acd-appservice/blob/master/CHANGELOG.md",
    },
    author="iKono Telecomomunicaciones S.A.S",
    author_email="desarrollo@ikono.com.co",
    description="An AppService created with the mautrix-python framework.",
    long_description=long_desc,
    long_description_content_type="text/markdown",
    packages=setuptools.find_packages(),
    install_requires=install_requires,
    extras_require=extras_require,
    python_requires="~=3.8",
    classifiers=[
        "Development Status :: 4 - Beta",
        "License :: OSI Approved :: GNU Affero General Public License v3 or later (AGPLv3+)",
        "Topic :: Communications :: Chat",
        "Framework :: AsyncIO",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
    ],
    package_data={
        "acd_appservice": [
            "example-config.yaml",
        ],
        "acd_appservice.web.api": ["components.yaml"],
    },
    data_files=[
        (".", ["acd_appservice/example-config.yaml"]),
    ],
)
