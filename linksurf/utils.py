import os


def get_env(name, cast=str):
    if name in os.environ:
        return cast(os.environ[name])
    else:
        raise KeyError("Missing env variable:", name)
