import os
import chromadb

class Vectors:
    def __init__(self, root):
        host = os.getenv("CHROMA_HOST")
        if host:
            token = os.getenv("CHROMA_AUTH_TOKEN")
            headers = {os.getenv("CHROMA_AUTH_HEADER", "Authorization"): token} if token else None
            self.client = chromadb.HttpClient(host=host, port=int(os.getenv("CHROMA_PORT", "8000")),
                ssl=os.getenv("CHROMA_SSL", "false").lower() == "true", headers=headers)
        else:
            self.client = chromadb.PersistentClient(path=str(root / "chroma"))

    def collection(self, revision):
        return self.client.get_or_create_collection("rev-" + revision, embedding_function=None,
                                                    metadata={"hnsw:space": "cosine"})

    def upsert(self, revision, chunks, embeddings):
        collection = self.collection(revision)
        collection.upsert(ids=[c["id"] for c in chunks], documents=[c["text"] for c in chunks],
                          metadatas=[c["metadata"] for c in chunks], embeddings=embeddings)

    def verify(self, revision, ids):
        actual = self.collection(revision).get(include=[])["ids"]
        if set(actual) != set(ids):
            raise ValueError("Index manifest does not match approved chunks")

    def indexed_ids(self, revision):
        return set(self.collection(revision).get(include=[])["ids"])

    def search(self, revision, dataset, embedding, count=5):
        collection = self.collection(revision)
        if not collection.count():
            return []
        result = collection.query(query_embeddings=[embedding], n_results=min(count, collection.count()),
                                  where={"dataset_id": dataset}, include=["documents", "metadatas", "distances"])
        return [{"citation": f"S{i+1}", "text": text, "metadata": meta, "distance": distance}
                for i, (text, meta, distance) in enumerate(zip(result["documents"][0], result["metadatas"][0], result["distances"][0]))]
