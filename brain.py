from openai import OpenAI

class Brain:

	def __init__(self):

		self.base_url = "https://openrouter.ai/api/v1"

		self.api_key = input("\nYour api key: ")

		self.client = OpenAI(

			base_url = self.base_url,

			api_key = self.api_key

		)

		self.model = "mistralai/mistral-small-3.1-24b-instruct:free"

	def ask(self, question):

		completion = self.client.chat.completions.create(

		  model=self.model,

		  messages=[

		    {
		      "role": "user",

		      "content": question
		    }
		  ]
		)

		answer = completion.choices[0].message.content

		return answer

