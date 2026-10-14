param location string
@minLength(13)
@maxLength(13)
param suffix string
param environmentName string
param principalId string
@secure()
param demoApiKey string
param maxSandboxes int
param webImageName string

var tags = {
  'azd-env-name': environmentName
}

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'logs-${suffix}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-${suffix}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
    workloadProfiles: [
      { name: 'Consumption', workloadProfileType: 'Consumption' }
    ]
  }
}

// The SDK and Microsoft Learn quickstarts currently use this preview contract.
// The type catalog may lag the service; see README for the contract reference.
#disable-next-line BCP081
resource sandboxGroup 'Microsoft.App/sandboxGroups@2026-02-01-preview' = {
  name: 'sandboxes-${suffix}'
  location: location
  tags: tags
  properties: {
    defaultCpu: '1'
    defaultMemory: '2Gi'
    defaultDisk: '20Gi'
    maxSandboxCount: maxSandboxes
    defaultTimeoutSeconds: 1800
  }
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: 'acr${suffix}'
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
  }
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${suffix}'
  location: location
  tags: tags
}

var acrPullRole = '7f951dda-4ed3-4680-a7ca-43fe172d538d'
resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, identity.id, acrPullRole)
  scope: registry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRole)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

var acrPushRole = '8311e382-0749-4cb8-b61a-304f252e45ec'
resource acrPush 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, principalId, acrPushRole)
  scope: registry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPushRole)
    principalId: principalId
  }
}

var sandboxOwnerRole = 'c24cf47c-5077-412d-a19c-45202126392c'
resource sandboxOwner 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(sandboxGroup.id, identity.id, sandboxOwnerRole)
  scope: sandboxGroup
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', sandboxOwnerRole)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-launchpad-${suffix}'
  location: location
  tags: union(tags, { 'azd-service-name': 'web' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  properties: {
    managedEnvironmentId: environment.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        allowInsecure: false
        targetPort: 8080
        transport: 'http'
      }
      secrets: [
        { name: 'demo-api-key', value: demoApiKey }
      ]
      registries: [
        { server: registry.properties.loginServer, identity: identity.id }
      ]
    }
    template: {
      containers: [
        {
          name: 'web'
          image: empty(webImageName) ? 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest' : webImageName
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            { name: 'DEMO_API_KEY', secretRef: 'demo-api-key' }
            { name: 'DEMO_MODE', value: 'azure' }
            { name: 'MAX_SANDBOXES', value: string(maxSandboxes) }
            { name: 'AZURE_CLIENT_ID', value: identity.properties.clientId }
            { name: 'AZURE_SUBSCRIPTION_ID', value: subscription().subscriptionId }
            { name: 'AZURE_RESOURCE_GROUP', value: resourceGroup().name }
            { name: 'AZURE_LOCATION', value: location }
            { name: 'AZURE_SANDBOX_GROUP', value: sandboxGroup.name }
          ]
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 1 }
    }
  }
  dependsOn: [acrPull, sandboxOwner]
}

output sandboxGroupName string = sandboxGroup.name
output registryEndpoint string = registry.properties.loginServer
output registryName string = registry.name
output environmentId string = environment.id
output appName string = app.name
output endpoint string = 'https://${app.properties.configuration.ingress.fqdn}'
