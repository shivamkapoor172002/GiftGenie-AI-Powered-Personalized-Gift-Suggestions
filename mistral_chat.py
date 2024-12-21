from mistralai import Mistral

# Replace with your actual API key
api_key = "fb7cL6YvR3KAgcY9I1kjp4qx4m78iK1M"
model = "mistral-large-latest"

# Initialize the client
client = Mistral(api_key=api_key)

# Create a chat completion
chat_response = client.chat.complete(
    model=model,
    messages=[
        {"role": "user", "content": "Who is the pm of india?"}
    ]
)

# Print the response
print(chat_response.choices[0].message.content)
