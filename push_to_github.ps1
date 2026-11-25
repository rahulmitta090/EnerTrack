# EnerTrack — Quick GitHub Push Script
# Usage: .\push_to_github.ps1 -RepoUrl "https://github.com/YOUR_USERNAME/YOUR_REPO.git"

param (
    [string]$RepoUrl
)

# Ensure Git is installed
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "==========================================================" -ForegroundColor Red
    Write-Host "Git is not installed or not found in your PATH." -ForegroundColor Yellow
    Write-Host "Please download and install Git from: https://git-scm.com/download/win" -ForegroundColor Cyan
    Write-Host "Or install via: winget install --id Git.Git -e --source winget" -ForegroundColor Cyan
    Write-Host "==========================================================" -ForegroundColor Red
    exit 1
}

# Prompt for GitHub URL if not provided
if (-not $RepoUrl) {
    Write-Host ""
    Write-Host "Please enter your GitHub repository URL:" -ForegroundColor Cyan
    Write-Host "(Example: https://github.com/username/enertrack.git)" -ForegroundColor DarkGray
    $RepoUrl = Read-Host "GitHub Repo URL"
}

if (-not $RepoUrl) {
    Write-Host "Error: No repository URL provided." -ForegroundColor Red
    exit 1
}

Write-Host "Initializing Git repository..." -ForegroundColor Cyan
if (-not (Test-Path ".git")) {
    git init
}

Write-Host "Staging files..." -ForegroundColor Cyan
git add .

Write-Host "Creating initial commit..." -ForegroundColor Cyan
git commit -m "Initial commit: EnerTrack — Energy Consumption Anomaly Detector"

Write-Host "Setting default branch to main..." -ForegroundColor Cyan
git branch -M main

Write-Host "Configuring remote origin..." -ForegroundColor Cyan
git remote remove origin 2>$null
git remote add origin $RepoUrl

Write-Host "Pushing code to GitHub..." -ForegroundColor Green
git push -u origin main

Write-Host ""
Write-Host "Successfully pushed EnerTrack to GitHub!" -ForegroundColor Green
