
from searcher import Search

from brain import Brain

import json

class Main:

	def __init__(self):

		self.rag = Search()

		self.brain = Brain()

		with open(persona_file, "r", encoding="utf-8") as f:

            data = json.load(f)

            self.persona = data.get("persona", "")

		self.question = ""

	def query(self):

		self.question = input("\nWelcome, you can talk with Mika: ")

		context = self.rag.query(self.question)

		prompt = f"""

		{self.persona}

		Context:

		{context}

		Question from user:

		{self.question}

		"""

		ans = self.brain.ask(prompt)

		print("\n" + ans)



main = Main()

while True:	

	main.query()