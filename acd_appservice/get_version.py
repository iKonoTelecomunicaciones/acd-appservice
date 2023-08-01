import os
import shutil
import subprocess

url_project = "https://gitlab.com/iKono/acd-appservice"
cmd_env = {
    "PATH": os.environ["PATH"],
    "HOME": os.environ["HOME"],
    "LANG": "C",
    "LC_ALL": "C",
}


def run(cmd):
    try:
        return (
            subprocess.check_output(cmd, stderr=subprocess.DEVNULL, env=cmd_env)
            .strip()
            .decode("ascii")
        )
    except (subprocess.CalledProcessError, subprocess.SubprocessError, OSError) as err:
        return None


def get_latest_tag():
    # Run the 'git describe --abbrev=0 --tags' command to get the latest development tag
    return run(["git", "describe", "--abbrev=0", "--tags"])


def get_latest_revision():
    # Run the 'git rev-parse HEAD' command to get the latest commit (revision)
    return run(["git", "rev-parse", "HEAD"])


def is_latest_revision_tag(git_tag):
    # Run the 'git describe --exact-match --tags' command to get the latest revision tag
    stable_tag = run(["git", "describe", "--exact-match", "--tags"])
    return True if stable_tag and stable_tag == git_tag else False


def update_init_file(version):
    with open("acd_appservice/__init__.py", "w") as init_file:
        init_file.write(f"# Generated from setup.py\n" f"__version__ = '{version}'")


# Get version project from gitlab repository
if os.path.exists(".git") and shutil.which("git"):
    # Gettting revision
    git_revision = get_latest_revision()
    git_revision = git_revision[:8] if git_revision else None
    git_revision_url = f"{url_project}/-/commit/{git_revision}" if git_revision else None

    # Getting tag
    git_tag = get_latest_tag()
    git_tag_url = f"{url_project}/-/tags/{git_tag}" if git_tag else None

    # Getting version project
    if git_tag and is_latest_revision_tag(git_tag):
        # if the tag is linked to latest commit, we update the version file
        update_init_file(git_tag[1:].replace("-", "."))
        version = git_tag[1:]
        linkified_version = f"[{git_tag}]({git_tag_url})"
    else:
        if git_tag and not git_tag.endswith("+dev"):
            # If the tag is not linked to latest commit, we add the revision to the developer version
            git_tag += "+dev"
        else:
            # If there is no tag, we use the revision as version
            git_tag = "v0.0.0.0+unknown"
        version = f"{git_tag[1:]}.{git_revision}"
        linkified_version = f"{git_tag}.[{git_revision}]({git_revision_url})"
