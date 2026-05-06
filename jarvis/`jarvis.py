import webbrowser
import requests

def jarvis(command):
    command = command.lower()
    
    if "open hindustan times" in command:
        webbrowser.open("https://www.hindustantimes.com")
        print("Opening Hindustan Times, sir.")
    
    elif "open bbc" in command:
        webbrowser.open("https://www.bbc.com/news")
        print("Opening BBC News, sir.")
    
    elif "weather" in command:
        print("Fetching weather for Mumbai, sir...")
        response = requests.get("https://wttr.in/Mumbai?format=3")
        print(response.text)
    
    else:
        print("I didn't quite catch that, sir. Could you rephrase?")

while True:
    user_input = input("You: ")
    if user_input.lower() in ["exit", "quit"]:
        print("Goodbye, sir.")
        break
    jarvis(user_input)