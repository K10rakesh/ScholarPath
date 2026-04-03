import google.generativeai as genai

genai.configure(api_key="GOOGLE_API_KEY")
model = genai.GenerativeModel("gemini-1.5-flash")
response = model.generate_content("Say hello")
print(response.text)