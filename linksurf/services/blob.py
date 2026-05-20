from linksurf.services.base import Service


class BlobStorage(Service):
    NAME = "blob_storage"

    def upload(self, blob: bytes, key: str):
        pass

    def download(self, key: str):
        pass
