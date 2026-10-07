import os

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

client = Groq(api_key=os.environ["GROQ_API_KEY"])

for model in client.models.list().data:
    print(model.id)

def generate_answer(question: str, context_chunks: list[str]) -> str:
    context = "\n\n".join(context_chunks)

    prompt = f"""Answer the question using only the context below. If the answer isn't in the context, say you don't know.

Context:
{context}

Question: {question}"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content

