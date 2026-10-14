targetScope = 'subscription'

@minLength(1)
@maxLength(32)
param environmentName string
param location string
param principalId string

@secure()
@minLength(16)
param demoApiKey string

@minValue(1)
@maxValue(50)
param maxSandboxes int = 50

param webImageName string = ''

var suffix = uniqueString(subscription().id, environmentName, location)

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: {
    'azd-env-name': environmentName
  }
}

module resources './resources.bicep' = {
  name: 'sandbox-launchpad-resources'
  scope: rg
  params: {
    location: location
    suffix: suffix
    environmentName: environmentName
    principalId: principalId
    demoApiKey: demoApiKey
    maxSandboxes: maxSandboxes
    webImageName: webImageName
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_LOCATION string = location
output AZURE_SANDBOX_GROUP string = resources.outputs.sandboxGroupName
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = resources.outputs.registryEndpoint
output AZURE_CONTAINER_REGISTRY_NAME string = resources.outputs.registryName
output AZURE_CONTAINER_APPS_ENVIRONMENT_ID string = resources.outputs.environmentId
output SERVICE_WEB_RESOURCE_NAME string = resources.outputs.appName
output SERVICE_WEB_ENDPOINT_URL string = resources.outputs.endpoint
