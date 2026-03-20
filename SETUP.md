Copy and paste the .env.example into your .env
(if the folder "credentials" under the root folder is not created, create it)
To get the google-vision.json file :
make sure you got 2FA in the google account you will use
-https://console.cloud.google.com/
-Select mealventory-ai project
-Go to IAM & Admin → Service Accounts
-Click mealventory-ai-service
-Go to keys 
-Click Add Key → Create New Key
-Choose JSON then create 
-Paste it under credentials
-Rename the .json file with the name google-vision.json