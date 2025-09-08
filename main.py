
from searcher import Search

from brain import Brain

from memory import Memory

import json

class Main:

	def __init__(self):

		self.rag = Search()

		self.brain = Brain()

		with open('persona.json', "r", encoding="utf-8") as f:

		    data = json.load(f)

		    self.persona = data.get("persona", "")

		self.question = ""

		self.memory = Memory(user_id="OO7")

	def query(self):

		self.question = input("\nWelcome, you can talk with Mika: ")

		context = self.rag.query(self.question)

		infos = self.memory.query(self.question)

		infos_str = ""

		for conv in infos:

		    infos_str += f"Q: {conv['question']}\nA: {conv['answer']}\n"

		prompt = f"""

		{self.persona}

		Context:

		{context}

		Question from user:

		{self.question}

		Some memory of the past conversations:

		{infos_str}

		"""

		ans = self.brain.ask(prompt)

		print("\n" + ans)

		self.memory.add_conversation(self.question, ans)



main = Main()

while True:	

	main.query()