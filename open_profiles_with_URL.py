import webbrowser

num_of_profiles = int(input("Enter the number of Chrome Profiles:"))
asin_url = str(input("Enter the ASIN URL:"))
print(num_of_profiles)
print(asin_url)
print("Opening URL in your Chrome Profiles...")
for i in range(num_of_profiles):
    chrome_path = f'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe %s --profile-directory="Profile {i}"'
    webbrowser.get(chrome_path).open(asin_url)
