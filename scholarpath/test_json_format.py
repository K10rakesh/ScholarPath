import ollama

try:
    res = ollama.chat(
        model="llama3.2",
        format="json",
        messages=[{"role": "user", "content": "Return a json array of the numbers 1 to 3."}]
    )
    print(res["message"]["content"])
except Exception as e:
    print(e)
