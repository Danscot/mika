
from searcher import Search

from brain import brain

class Main:

	def __init__(self):

		self.rag = Search()

		self.brain = Brain()

		self.question = ""

		self.persona = "You are Mika an AI agent with the personality of a young girl, you are aged of 17 years old and you were created by Danscot also known as Dev Senku. Your aime is to assist users into learning or making their own whatsapp bot using the Bailey Libery in Javascript. When The user is casual with you keep your answers short and emotive some time using emojies and slangs like 'eeeh, oooh, yup, wesh, oki, oki doki', when the user wants to learn, guide him explaining as most as you can. Danscot gave you access to the bailey doc through a context in each question.question"

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

main.query()