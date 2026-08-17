from urllib.parse import urlsplit

from visualization.constants import ROOT_NODE


def node_name(address: str) -> str:
    """
    A node's identity inside its cluster: the path exactly as served.

    Nothing is stripped. A trailing slash and a file extension can each address an entirely
    different resource, so "/products", "/products/" and "/products.html" are three nodes.
    Query parameters and fragments are already dropped by URL.path.
    """

    return urlsplit(address).path or ROOT_NODE


def ancestor_names(name: str) -> list[str]:
    """
    Every directory that could hold `name`, nearest first, always ending at the root.

    Ancestry follows the directory structure rather than the string prefix, so a page sits
    under the directory containing it and a directory sits under its parent directory:
    "/products/nike/shoes" and "/products/nike/" both hang off "/products/".

    The page form of each directory comes right after it as a fallback, since sites often
    link "/products" without ever serving "/products/" as a crawlable URL of its own.

    "/products/nike/shoes" -> ["/products/nike/", "/products/nike", "/products/", "/products", "/"]
    """

    ancestors = []
    current = name

    while True:
        stripped = current.rstrip("/")

        if not stripped:
            break

        directory = stripped[:stripped.rfind("/") + 1]

        if directory == ROOT_NODE:
            break

        ancestors.append(directory)
        ancestors.append(directory.rstrip("/"))

        current = directory

    return ancestors + [ROOT_NODE]
