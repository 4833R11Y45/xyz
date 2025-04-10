git checkout merge_branches_test
git pull origin merge_branches_test
docker build -t spendconsole-java:latest .
az acr login -n SpendConsoleAi
docker tag spendconsole-java spendconsoleai.azurecr.io/spend_console:v2
docker push spendconsoleai.azurecr.io/spend_console:v2