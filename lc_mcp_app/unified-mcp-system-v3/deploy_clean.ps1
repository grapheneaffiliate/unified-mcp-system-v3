# Clean deployment script for unified MCP system
$token = $env:GITHUB_PERSONAL_ACCESS_TOKEN
$repoName = "unified-mcp-system-v2"
$description = "Unified MCP System v2: Production-ready MCP server with OpenAI-compatible gateway"

if (-not $token) {
    Write-Host "❌ Error: GITHUB_PERSONAL_ACCESS_TOKEN environment variable not set" -ForegroundColor Red
    exit 1
}

$headers = @{
    "Authorization" = "token $token"
    "Accept" = "application/vnd.github.v3+json"
    "Content-Type" = "application/json"
}
$body = "{`"name`":`"$repoName`",`"description`":`"$description`",`"private`":false}"

Write-Host "🚀 Creating clean GitHub repository..." -ForegroundColor Blue
try {
    $response = Invoke-RestMethod -Uri "https://api.github.com/user/repos" -Method Post -Headers $headers -Body $body
    Write-Host "✓ Repository created: $($response.html_url)" -ForegroundColor Green
    
    # Set up git
    git branch -M main
    git remote add origin $response.clone_url
    
    # Push to GitHub
    Write-Host "📤 Pushing to GitHub..." -ForegroundColor Blue
    git push -u origin main
    Write-Host "✓ Code pushed successfully!" -ForegroundColor Green
    
    # Create tag
    Write-Host "🏷️ Creating release tag..." -ForegroundColor Blue
    git tag -a v2.0.0 -m "Unified MCP System v2.0.0 - Production-ready with GPT-5 improvements"
    git push origin v2.0.0
    Write-Host "✓ Tag created successfully!" -ForegroundColor Green
    
    Write-Host "🎉 Clean repository deployment complete!" -ForegroundColor Green
    Write-Host "Repository URL: $($response.html_url)" -ForegroundColor Yellow
}
catch {
    Write-Host "❌ Error: $($_.Exception.Message)" -ForegroundColor Red
}
