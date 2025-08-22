# PowerShell script to create GitHub repository for quantum-rtsc-protocol

# Set repository details
$repoName = "quantum-rtsc-protocol"
$description = "Lab-Reproducible Protocol for Room-Temperature Superconductivity Verification - Complete implementation with Allen-Dynes calculations, test suite, and LaTeX documentation"
$isPrivate = $false

# Check if GitHub CLI is available
if (Get-Command gh -ErrorAction SilentlyContinue) {
    Write-Host "Creating GitHub repository using GitHub CLI..."
    
    # Create the repository
    if ($isPrivate) {
        gh repo create $repoName --description $description --private --source=quantum-rtsc-protocol --remote=origin --push
    } else {
        gh repo create $repoName --description $description --public --source=quantum-rtsc-protocol --remote=origin --push
    }
    
    Write-Host "Repository created successfully!"
    Write-Host "Repository URL: https://github.com/$(gh api user --jq .login)/$repoName"
} else {
    Write-Host "GitHub CLI not found. Please install GitHub CLI or create repository manually."
    Write-Host "Repository name: $repoName"
    Write-Host "Description: $description"
    Write-Host ""
    Write-Host "Manual steps:"
    Write-Host "1. Go to https://github.com/new"
    Write-Host "2. Create repository named: $repoName"
    Write-Host "3. Add description: $description"
    Write-Host "4. Make it public"
    Write-Host "5. Don't initialize with README (we already have files)"
    Write-Host "6. Run these commands in quantum-rtsc-protocol directory:"
    Write-Host "   git remote add origin https://github.com/YOUR_USERNAME/$repoName.git"
    Write-Host "   git branch -M main"
    Write-Host "   git push -u origin main"
}
