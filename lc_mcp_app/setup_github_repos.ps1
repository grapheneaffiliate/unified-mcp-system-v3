# PowerShell script to set up GitHub repositories for the transformed MCP projects
# Run this script from the parent directory containing both model_context_server and lc_mcp_app

Write-Host "🚀 Setting up GitHub repositories for MCP projects..." -ForegroundColor Green

# Check if git is installed
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Git is not installed or not in PATH" -ForegroundColor Red
    exit 1
}

# Check if GitHub CLI is installed (optional but recommended)
$ghInstalled = Get-Command gh -ErrorAction SilentlyContinue
if ($ghInstalled) {
    Write-Host "✅ GitHub CLI detected - will use for repository creation" -ForegroundColor Green
} else {
    Write-Host "⚠️  GitHub CLI not found - you'll need to create repositories manually" -ForegroundColor Yellow
}

# Function to setup a repository
function Setup-Repository {
    param(
        [string]$ProjectPath,
        [string]$RepoName,
        [string]$Description,
        [string]$CommitMessage,
        [string]$TagVersion,
        [string]$TagMessage
    )
    
    Write-Host "📁 Setting up repository: $RepoName" -ForegroundColor Cyan
    
    # Navigate to project directory
    if (-not (Test-Path $ProjectPath)) {
        Write-Host "❌ Project path not found: $ProjectPath" -ForegroundColor Red
        return $false
    }
    
    Set-Location $ProjectPath
    
    # Initialize git repository
    Write-Host "  🔧 Initializing git repository..." -ForegroundColor Yellow
    git init
    
    # Add all files
    Write-Host "  📦 Adding files..." -ForegroundColor Yellow
    git add .
    
    # Create initial commit
    Write-Host "  💾 Creating initial commit..." -ForegroundColor Yellow
    git commit -m $CommitMessage
    
    # Set main branch
    git branch -M main
    
    # Create repository on GitHub (if gh CLI is available)
    if ($ghInstalled) {
        Write-Host "  🌐 Creating GitHub repository..." -ForegroundColor Yellow
        gh repo create "grapheneaffiliate/$RepoName" --description $Description --public --source . --push
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  ✅ Repository created and pushed successfully!" -ForegroundColor Green
        } else {
            Write-Host "  ❌ Failed to create repository with GitHub CLI" -ForegroundColor Red
            Write-Host "  📝 Manual setup required:" -ForegroundColor Yellow
            Write-Host "     1. Create repository: https://github.com/new" -ForegroundColor White
            Write-Host "     2. Repository name: $RepoName" -ForegroundColor White
            Write-Host "     3. Description: $Description" -ForegroundColor White
            Write-Host "     4. Run: git remote add origin https://github.com/grapheneaffiliate/$RepoName.git" -ForegroundColor White
            Write-Host "     5. Run: git push -u origin main" -ForegroundColor White
        }
    } else {
        Write-Host "  📝 Manual repository creation required:" -ForegroundColor Yellow
        Write-Host "     1. Go to: https://github.com/new" -ForegroundColor White
        Write-Host "     2. Owner: grapheneaffiliate" -ForegroundColor White
        Write-Host "     3. Repository name: $RepoName" -ForegroundColor White
        Write-Host "     4. Description: $Description" -ForegroundColor White
        Write-Host "     5. Public repository" -ForegroundColor White
        Write-Host "     6. Do NOT initialize with README" -ForegroundColor White
        Write-Host "" -ForegroundColor White
        Write-Host "  After creating the repository, run these commands:" -ForegroundColor Yellow
        Write-Host "     git remote add origin https://github.com/grapheneaffiliate/$RepoName.git" -ForegroundColor White
        Write-Host "     git push -u origin main" -ForegroundColor White
    }
    
    # Create and push tag
    Write-Host "  🏷️  Creating release tag: $TagVersion" -ForegroundColor Yellow
    git tag -a $TagVersion -m $TagMessage
    
    if ($ghInstalled -and $LASTEXITCODE -eq 0) {
        git push origin $TagVersion
        Write-Host "  ✅ Tag pushed successfully!" -ForegroundColor Green
    } else {
        Write-Host "  📝 After setting up remote, run: git push origin $TagVersion" -ForegroundColor Yellow
    }
    
    Write-Host "  ✅ $RepoName setup complete!" -ForegroundColor Green
    Write-Host ""
    
    return $true
}

# Setup MCP Agent Server
$mcpServerPath = ".\model_context_server"
$mcpCommitMessage = @"
feat: transform monolithic MCP server into production-ready architecture

- Implement modular package structure with mcp_agent/
- Add comprehensive security (auth, rate limiting, sandboxing)
- Add enterprise observability (structured logging, Prometheus metrics)
- Add modern packaging with pyproject.toml
- Add Docker deployment with multi-stage builds
- Add testing framework with pytest
- Add CI/CD with GitHub Actions
- Add comprehensive documentation

Transforms 1,400-line main.py into clean, maintainable, extensible system
following GPT-5 recommendations for production readiness.
"@

Setup-Repository -ProjectPath $mcpServerPath -RepoName "mcp-agent-server" -Description "Production-ready Model Context Protocol server with enterprise security, observability, and 25+ tools" -CommitMessage $mcpCommitMessage -TagVersion "v1.0.0" -TagMessage "Production-ready MCP server with enterprise features"

# Setup LC MCP App
$lcmcpAppPath = ".\lc_mcp_app"
$lcmcpCommitMessage = @"
feat: transform LangChain MCP intermediary into production-ready service

- Implement modular architecture with lc_mcp_app/ package
- Add ASGI lifespan management for proper startup/shutdown
- Add connection pooling and timeout budgets for MCP client
- Add OpenAI-compatible streaming and non-streaming endpoints
- Add comprehensive middleware (auth, rate limiting, metrics)
- Add structured logging with correlation IDs
- Add Docker deployment and CI/CD pipeline
- Add testing framework and development tooling

Enhances original intermediary with GPT-5 production improvements:
back-pressure handling, real OpenAI compatibility, security by default.
"@

Setup-Repository -ProjectPath $lcmcpAppPath -RepoName "lc-mcp-app" -Description "LangChain MCP intermediary with OpenAI-compatible API for seamless integration" -CommitMessage $lcmcpCommitMessage -TagVersion "v0.1.0" -TagMessage "Production-ready LangChain MCP intermediary"

Write-Host "🎉 Repository setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "📋 Summary:" -ForegroundColor Cyan
Write-Host "  • MCP Agent Server: https://github.com/grapheneaffiliate/mcp-agent-server" -ForegroundColor White
Write-Host "  • LC MCP App: https://github.com/grapheneaffiliate/lc-mcp-app" -ForegroundColor White
Write-Host ""
Write-Host "🚀 Next steps:" -ForegroundColor Cyan
Write-Host "  1. Test your local setup: make dev (in each project)" -ForegroundColor White
Write-Host "  2. Deploy with Docker: docker-compose up --build" -ForegroundColor White
Write-Host "  3. Share with the MCP community!" -ForegroundColor White
Write-Host ""
Write-Host "✨ Your 'works on my machine' prototypes are now production-ready!" -ForegroundColor Green
