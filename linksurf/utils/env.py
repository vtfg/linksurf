import os


def get_env(name, cast: type = str, default: str | int = None, required: bool = True):
    if name in os.environ:
        return cast(os.environ[name])
    elif default is not None:
        return cast(default)
    elif not required:
        return None
    else:
        raise KeyError("Missing env variable:", name)
