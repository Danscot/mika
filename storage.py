import faiss
"""
Purpose: save/load FAISS index and chunks.
"""
class Storage:
    def save_index(self, index, path="index.faiss"):
        faiss.write_index(index, path)

    def load_index(self, path="index.faiss"):
        return faiss.read_index(path)

    def save_chunks(self, chunks, path="chunks.pkl"):
        with open(path, "wb") as f:
            pickle.dump(chunks, f)

    def load_chunks(self, path="chunks.pkl"):
        with open(path, "rb") as f:
            return pickle.load(f)
