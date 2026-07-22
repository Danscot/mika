'''
Just implementing a user memory to recall conversation by storing everything in a faiss format hehehe math vect shith
'''
import os

import faiss

import numpy as np

import pickle

from embedder import Embedder  


class Memory:

    def __init__(self, user_id: str, index_dir="user_indexes"):

        self.user_id = user_id

        self.index_dir = index_dir

        os.makedirs(self.index_dir, exist_ok=True)

        # File path for this user's FAISS index and mapping
        self.index_path = os.path.join(self.index_dir, f"{self.user_id}_index.faiss")

        self.data_path = os.path.join(self.index_dir, f"{self.user_id}_data.pkl")

        # Initialize embedder
        self.embedder = Embedder()

        # Load or create FAISS index
        if os.path.exists(self.index_path) and os.path.exists(self.data_path):

            self.index = faiss.read_index(self.index_path)

            with open(self.data_path, "rb") as f:

                self.data = pickle.load(f)

        else:

            self.index = None

            self.data = []  # store list of {"question": ..., "answer": ...}

    def add_conversation(self, question: str, answer: str):

        """
        Store a conversation: question + answer
        """

        # Embed the combined conversation

        text = f"Q: {question}\nA: {answer}"

        embedding = self.embedder.embed([text])  # returns numpy array

        if self.index is None:

            dim = embedding.shape[1]

            self.index = faiss.IndexFlatL2(dim)

        # Add to FAISS index

        self.index.add(embedding)

        self.data.append({"question": question, "answer": answer})

        # Save index + data

        faiss.write_index(self.index, self.index_path)

        with open(self.data_path, "wb") as f:

            pickle.dump(self.data, f)

    def query(self, query_text: str, top_k: int = 5):

        """
        Retrieve top_k relevant conversations for a query

        """

        if self.index is None or len(self.data) == 0:

            return []

        query_emb = self.embedder.embed([query_text])

        distances, indices = self.index.search(query_emb, top_k)

        results = []

        for idx in indices[0]:

            if idx < len(self.data):
            	
                results.append(self.data[idx])

        return results
