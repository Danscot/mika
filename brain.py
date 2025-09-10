from openai import OpenAI

import os

class Brain:

    def __init__(self):

        self.base_url = "https://openrouter.ai/api/v1"

        self.api_key = os.getenv("AI")

        self.client = OpenAI(

            base_url = self.base_url,

            api_key = self.api_key

        )

        self.model = "mistralai/mistral-small-3.1-24b-instruct:free"

    def ask(self, prompt):

        completion = self.client.chat.completions.create(

            model=self.model,

            messages=[{"role": "user", "content": prompt}]
        )

        answer = completion.choices[0].message.content

        # Try to split code from explanation
        if "```" in answer:

            parts = answer.split("```")

            explanation = parts[0].strip()

            code = parts[1].replace("javascript", "").strip() if len(parts) > 1 else ""

            return {"text": explanation, "code": code}
            
        return {"text": answer, "code": ""}

