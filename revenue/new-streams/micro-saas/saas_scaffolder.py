"""
Micro-SaaS Generator Framework
Rapidly scaffolds and deploys niche SaaS products via Sites.
"""

import json
from datetime import datetime
from pathlib import Path

class MicroSaasScaffolder:
    def __init__(self):
        self.projects_dir = Path("/Agentic/revenue/new-streams/micro-saas/projects")
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.templates = {
            "api-wrapper": {"stack": "node", "billing": "stripe", "deploy": "sites"},
            "dashboard-as-service": {"stack": "nextjs", "billing": "lemon-squeezy", "deploy": "sites"},
            "ai-tool": {"stack": "python-fastapi", "billing": "stripe", "deploy": "sites"}
        }
        
    def scaffold_project(self, name: str, template: str, niche: str) -> dict:
        """Generate project structure and deployment manifest."""
        if template not in self.templates:
            raise ValueError(f"Unknown template: {template}")
            
        config = self.templates[template]
        project = {
            "name": name,
            "niche": niche,
            "template": template,
            "stack": config["stack"],
            "billing_provider": config["billing"],
            "deployment_target": config["deploy"],
            "created_at": datetime.utcnow().isoformat(),
            "status": "scaffolded",
            "files": [
                f"{name}/package.json" if config["stack"] != "python-fastapi" else f"{name}/requirements.txt",
                f"{name}/src/index.{'ts' if 'node' in config['stack'] or 'nextjs' in config['stack'] else 'py'}",
                f"{name}/billing/{config['billing']}.config.js",
                f"{name}/sites.deploy.json"
            ],
            "next_steps": [
                "Implement core business logic",
                "Configure billing webhooks",
                "Set up analytics tracking",
                "Deploy to Sites via u_mcp__codex_apps__sites"
            ]
        }
        
        output_path = self.projects_dir / f"{name}_manifest.json"
        with open(output_path, 'w') as f:
            json.dump(project, f, indent=2)
            
        return {"status": "scaffolded", "manifest": str(output_path), "project": project}
    
    def list_projects(self) -> list:
        """List all scaffolded micro-SaaS projects."""
        manifests = list(self.projects_dir.glob("*_manifest.json"))
        projects = []
        for m in manifests:
            with open(m) as f:
                projects.append(json.load(f))
        return projects

if __name__ == "__main__":
    scaffolder = MicroSaasScaffolder()
    result = scaffolder.scaffold_project("crypto-alert-saas", "api-wrapper", "Crypto Trading Alerts")
    print(json.dumps(result, indent=2))
