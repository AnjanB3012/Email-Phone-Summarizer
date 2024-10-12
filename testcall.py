import os.path
import base64
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from email.utils import parsedate_to_datetime
import google.generativeai as genai
import google.generativeai as genai1
from datetime import datetime, timedelta, timezone
import os
import azure.cognitiveservices.speech as speechsdk
from openai import AzureOpenAI
import time
from twilio.rest import Client

account_sid = ''
auth_token = ''
Client = Client(account_sid,auth_token)
to_number = ''
from_number = ''


os.environ["AZURE_OPENAI_API_KEY"] = ""  # Use os.environ to set environment variables
os.environ["AZURE_OPENAI_ENDPOINT"] = ""
os.environ["AZURE_OPENAI_CHAT_DEPLOYMENT"] = ""
os.environ["SPEECH_KEY"] = ""
os.environ["SPEECH_REGION"] = ""

speech_config = speechsdk.SpeechConfig(subscription=os.environ.get('SPEECH_KEY'), region=os.environ.get('SPEECH_REGION'))
speech_config.speech_synthesis_voice_name='en-US-AvaMultilingualNeural'
audio_output_config = speechsdk.audio.AudioOutputConfig(filename="output.wav")
# audio_config = speechsdk.audio.AudioConfig(use_default_microphone=True)
speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_output_config)
# speech_config.speech_recognition_language="en-US"
# speech_recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)

# Configure Google Generative AI
genai.configure(api_key="")
genai1.configure(api_key="")
model_info = genai.get_model('models/gemini-1.5-pro-002')
# Define the necessary scopes for Gmail API
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def speechRecognizer(inputtext):
    startindex = 0
    endindex = 0
    for i in range(0,len(inputtext)):
        if(inputtext[i:i+8]=="<speech>"):
            startindex = i+8
            break
    for j in range(0,len(inputtext)):
        if(inputtext[j:j+9]=="</speech>"):
            endindex = j
            break
    return inputtext[startindex:endindex]

def format_email(message, headers, email_body):
    """Formats the email content into the desired string format."""
    sender = ""
    date_sent = ""
    subject = ""

    # Extract sender, date, and subject from headers
    for header in headers:
        if header['name'] == 'From':
            sender = header['value']
        if header['name'] == 'Date':
            date_sent = parsedate_to_datetime(header['value']).strftime('%Y-%m-%d %H:%M:%S')
        if header['name'] == 'Subject':
            subject = header['value']
    
    # Format the email into the desired string
    formatted_email = f"<{sender}>\n{{{date_sent}}}\n{{{subject}}}\n{email_body}\n</email>\n\n"
    return formatted_email

def get_email_content(service, message_id):
    """Fetches the full content of an email."""
    try:
        # Get the full message in MIME format
        message = service.users().messages().get(userId='me', id=message_id, format='full').execute()
        headers = message['payload']['headers']
        
        # Get the body of the email (which is base64-encoded)
        parts = message['payload'].get('parts', [])
        email_body = ""

        # Extract the plain text part (you can modify this to handle HTML or attachments)
        for part in parts:
            if part['mimeType'] == 'text/plain':  # Extract plain text part
                email_body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                break
        else:
            # Fallback if no plain text part is found
            email_body = base64.urlsafe_b64decode(message['payload']['body']['data']).decode('utf-8')

        # Return the formatted email string
        return format_email(message, headers, email_body)

    except HttpError as error:
        print(f'An error occurred while fetching message ID {message_id}: {error}')
        return None

def authenticate_gmail_api(inputhours):
    """Authenticate and connect to Gmail API."""
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is created automatically
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    # If no valid credentials, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    try:
        # Build the Gmail API service
        service = build('gmail', 'v1', credentials=creds)
        
        # Calculate one hour ago time in RFC 3339 format (used by Gmail API)
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=inputhours)
        
        # Convert to Unix timestamp for Gmail query
        query_time = int(one_hour_ago.timestamp())

        # Get messages from past hour using query parameter 'after'
        results = service.users().messages().list(userId='me', q=f'after:{query_time}').execute()
        messages = results.get('messages', [])

        if not messages:
            print('No messages found.')
            return ""

        # Initialize all_emails to store email content
        email_list = []
        # all_emails = ""
        
        # Loop through each message and append the full content to the string
        for message in messages:
            #print(f"Fetching message ID: {message['id']}")
            email_content = get_email_content(service, message['id'])
            if email_content:
                email_list.append(email_content)
                # all_emails += email_content
        numberCompleted = 0
        generation_config = {
            "temperature": 1,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 8192,
            "response_mime_type": "text/plain",
        }

        model = genai1.GenerativeModel(
            model_name="gemini-1.5-pro-002",
            generation_config=generation_config,
            # safety_settings = Adjust safety settings
            # See https://ai.google.dev/gemini-api/docs/safety-settings
            system_instruction="You are an AI assistant designed to provide another AI model with email summaries so that it can talk to the customer summarizing his/her emails.\nYou will be given emails in the following format:\n<sender_details>\n{date_of_email time_of_email}\n{subject_of_email}\ncontent_of_email\n</email>\nYou will create a short summary of each email concisely so that it covers all important information of the email but ignores any unnecassry details like url or anything else. if there is no content in the email just send no content. \nYour output should be in the following format(Note: do not miss any space or bracket such as <> or {} for indexing purposes):\n<sender_details>\n{date_of_email time_of_email}\n{subject_of_email}\nyour_summary_of_email_goes_here\n</email>",
        )

        chat_session1 = model.start_chat(
            history=[
            ]
        )
        while numberCompleted<len(email_list):
            try:
                response = chat_session1.send_message(email_list[numberCompleted])
                email_list[numberCompleted] = response.text 
                numberCompleted+=1
            except Exception as error1:
                generation_config = {
                    "temperature": 1,
                    "top_p": 0.95,
                    "top_k": 40,
                    "max_output_tokens": 8192,
                    "response_mime_type": "text/plain",
                }

                model = genai1.GenerativeModel(
                    model_name="gemini-1.5-pro-002",
                    generation_config=generation_config,
                    # safety_settings = Adjust safety settings
                    # See https://ai.google.dev/gemini-api/docs/safety-settings
                    system_instruction="You are an AI assistant designed to provide another AI model with email summaries so that it can talk to the customer summarizing his/her emails.\nYou will be given emails in the following format:\n<sender_details>\n{date_of_email time_of_email}\n{subject_of_email}\ncontent_of_email\n</email>\nYou will create a short summary of each email concisely so that it covers all important information of the email but ignores any unnecassry details like url or anything else. if there is no content in the email just send no content. \nYour output should be in the following format(Note: do not miss any space or bracket such as <> or {} for indexing purposes):\n<sender_details>\n{date_of_email time_of_email}\n{subject_of_email}\nyour_summary_of_email_goes_here\n</email>",
                )
                chat_session1 = model.start_chat(
                    history=[
                    ]
                )
                print("Exception!")
                time.sleep(60)
        
        return email_list

    except HttpError as error:
        print(f'An error occurred while authenticating: {error}')



def executer(hoursneeded,all_emails,numberOfConversations,history):
    model = genai.GenerativeModel('models/gemini-1.5-pro-002')

    generation_config1 = {
    "temperature": 1.5,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 8192,
    "response_mime_type": "text/plain",
    }
    if all_emails:
        # print(all_emails)
        print(model.count_tokens(all_emails).total_tokens)
        if(int(model.count_tokens(all_emails).total_tokens)<2000000):
            model = genai.GenerativeModel(
            model_name="gemini-1.5-pro-002",
            generation_config=generation_config1,
            # safety_settings = Adjust safety settings
            # See https://ai.google.dev/gemini-api/docs/safety-settings
            system_instruction="You are an artificial intelligence call assistant who generates speech for an assistant to talk. You should summarize the email data being given to you by another model which summarizes emails and gives you a condensed summary to avoid overload, in the following format:\n<sender_details>\n{date_of_email time_of_email}\n{subject_of_email}\ncontent_of_email\n</email>\nYou will get your data in the following way:\n<conversation_id=convo_id>(from 0 to infinity incremental)\nmessages one by one in the above format\n</conversation>\nthe email contents will be sent as a pipeline one by one.\nYou need to summarize all the emails in the given timeframe(which will be provided in the prompt) and remember the users' preferences of knowing emails such as if they don't want to hear from any particular newsletter or job portal or scam advertisements do not summarize to them those emails. Also since you are a call based assistant try to keep it as concise and user friendly as possible similair to news headlines. Since this goes into a speech service your output should follow proper consistent output in the following format to index it right.\n<speech>\nyour_speech_that_the_user_should_hear\n</speech>\n<non_speech>\nWrite_down_notes_to_remember_user_preferences_you_need_to_use_this_later\n</non_speech>\nAny User will be in the following format:\n<user_speech>\nUsers_speech\n</user_speech>\nAlso don't forget the following points: You are an assistant and respond like an assistant with warmth to the user, when a user says something respond with affirmation, also do not tell the user the time of the email unless asked to and so goes with the sender unless suitable for the situation or asked by the user, also keep the summaries as a conversational tone unlike reciting one by one, merge together and keep a flow while keeping the seperation between each email.\n Also Don't makeup any new emails use only the input emails.",
            )
            history.append(
                    {
                        "role":"user",
                        "parts":[
                            "<conversation_id="+str(numberOfConversations)+">\n",
                        ]
                    }
                )
            for emails in all_emails:
                history.append(
                    {
                        "role":"user",
                        "parts":[
                            emails,
                        ]
                    }
                )
            chat_session = model.start_chat(
                history=history
            )
            terminate = False
            inputmsg = "TimeFrame="+str(hoursneeded)+" Hours;\n"
            response = chat_session.send_message(inputmsg)
            history.append(
                    {
                        "role":"user",
                        "parts":[
                            inputmsg,
                        ]
                    }
                )
            history.append(
                {
                        "role":"model",
                        "parts":[
                            response.text
                        ]
                    }
            )
            try:
                os.remove("output.wav")
            except Exception as err:
                emptyvar = 0
            speech_synthesizer.speak_text_async(speechRecognizer(str(response.text))).get()
            call = Client.calls.create(
                twiml="<Response><Play>http://..../output.wav</Play></Response>",
                to=to_number,
                from_=from_number
            )
            print(call.sid)
            # while(terminate == False):
            #     speech_recognition_result = speech_recognizer.recognize_once_async().get()
            #     if speech_recognition_result.reason == speechsdk.ResultReason.RecognizedSpeech:
            #         inputspeech = "<user_speech>\n"+speech_recognition_result.text+"\n</user_speech>"
            #         response = chat_session.send_message(inputspeech)
            #         history.append(
            #                 {
            #                     "role":"user",
            #                     "parts":[
            #                         inputspeech,
            #                     ]
            #                 }
            #         )
            #         history.append(
            #             {
            #                     "role":"model",
            #                     "parts":[
            #                         response.text
            #                     ]
            #                 }
            #         )
            #         try:
            #             os.remove("output.wav")
            #         except Exception as err:
            #             emptyvar = 0
            #         speech_synthesizer.speak_text_async(speechRecognizer(str(response.text))).get()
            #     else:
            #         history.append(
            #             {
            #                 "role":"user",
            #                 "parts":[
            #                     "/conversation>"
            #                 ]
            #             }
            #         )
            #         numberOfConversations+=1
            #         terminate = True
            # print(response.text)
            # print(speechRecognizer(str(response.text)))
    else:
        print("No emails retrieved.")
    finallist = [hoursneeded,all_emails,numberOfConversations,history]
    return finallist






# Execute the function directly
hoursneeded = int(input("How many hours old emails do you need?"))
all_emails = authenticate_gmail_api(hoursneeded)
numberOfConversations = 0
last_conversation = datetime.now(timezone.utc)
history = []
returnedList = executer(hoursneeded=hoursneeded,all_emails=all_emails,numberOfConversations=numberOfConversations,history=history)
hoursneeded = returnedList[0]
all_emails = returnedList[1]
numberOfConversations = returnedList[2]
history = returnedList[3]

while(True):
    if(int((datetime.now(timezone.utc)-last_conversation).total_seconds())>=hoursneeded*3600):
        last_conversation = datetime.now(timezone.utc)
        returnedList = executer(hoursneeded=hoursneeded,all_emails=all_emails,numberOfConversations=numberOfConversations,history=history)
        hoursneeded = returnedList[0]
        all_emails = returnedList[1]
        numberOfConversations = returnedList[2]
        history = returnedList[3]