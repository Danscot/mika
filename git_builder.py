'''
this builder is to be able to update the index.faiss directly with data from github
'''

import os
import git
import pickle
import faiss
from embedder import Embedder
from indexer import Indexer
from storage import Storage


class GitHubBuilder:
    def __init__(self, repo_url, repo_dir="repo_cache"):
        self.repo_url = repo_url
        self.repo_dir = repo_dir
        self.embedder = Embedder()
        self.storage = Storage()

    def clone_repo(self):
        if not os.path.exists(self.repo_dir):
            print(f"📥 Cloning {self.repo_url}...")
            git.Repo.clone_from(self.repo_url, self.repo_dir)
        else:
            print("🔄 Repo already exists, pulling latest...")
            repo = git.Repo(self.repo_dir)
            repo.remotes.origin.pull()

    def load_files(self, exts=[".py", ".js", ".ts", ".md"]):
        """Collect code/docs files into text chunks"""
        print("📂 Collecting files...")
        chunks = []
        for root, _, files in os.walk(self.repo_dir):
            for file in files:
                if any(file.endswith(ext) for ext in exts):
                    path = os.path.join(root, file)
                    try:
                        with open(path, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                            chunks.append(f"FILE: {file}\n{content}")
                    except Exception as e:
                        print(f"⚠️ Could not read {file}: {e}")
        return chunks

    def build_base(
        self,
        index_path="index.faiss",
        chunks_path="chunks.pkl",
        append=False,
    ):
        """Build or extend FAISS index with a GitHub repo"""
        self.clone_repo()
        chunks = self.load_files()

        print("🧮 Embedding repo files...")
        embeddings = self.embedder.embed(chunks)

        # If append mode and index already exists
        if append and os.path.exists(index_path) and os.path.exists(chunks_path):
            print("➕ Appending to existing index...")
            index = faiss.read_index(index_path)

            # Just use Indexer.append_to_index
            indexer = Indexer(index.d)
            indexer.index = index
            index = indexer.append_to_index(embeddings)

            # Merge old + new chunks
            with open(chunks_path, "rb") as f:
                old_chunks = pickle.load(f)
            chunks = old_chunks + chunks

        else:
            print("📦 Building new FAISS index...")
            dim = embeddings.shape[1]
            indexer = Indexer(dim)
            index = indexer.build_index(embeddings)

        print("💾 Saving index + chunks...")
        self.storage.save_index(index, index_path)
        self.storage.save_chunks(chunks, chunks_path)

        print("✅ GitHub repo indexed successfully!")


if __name__ == "__main__":

	git = input("enter the github page link: ")

    # Example: Index Baileys repo and append to existing knowledge
	builder = GitHubBuilder(git)

    builder.build_base(append=True)
