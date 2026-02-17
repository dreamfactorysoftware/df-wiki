#!/usr/bin/env python3
"""
update_messaging.py - Update DreamFactory positioning on Priority 1 wiki pages.

Replaces outdated messaging with the golden anchor statements:
  Short: "DreamFactory is a self-hosted platform providing governed API access
          to any data source for enterprise apps and local LLMs."
  Long:  "DreamFactory is a secure, self-hosted enterprise data access platform
          that provides governed API access to any data source, connecting
          enterprise applications and on-prem LLMs with role-based access and
          identity passthrough."
"""

import mwclient

ANCHOR_SHORT = (
    "DreamFactory is a self-hosted platform providing governed API access "
    "to any data source for enterprise apps and local LLMs."
)
ANCHOR_LONG = (
    "DreamFactory is a secure, self-hosted enterprise data access platform "
    "that provides governed API access to any data source, connecting "
    "enterprise applications and on-prem LLMs with role-based access "
    "and identity passthrough."
)

SUMMARY = "Update DreamFactory positioning to golden anchor messaging"


def connect():
    site = mwclient.Site("localhost:8082", path="/", scheme="http")
    site.force_login = False
    return site


def update_page(site, name, replacements):
    """Apply a list of (old, new) string replacements to a wiki page."""
    page = site.pages[name]
    text = page.text()
    original = text
    for old, new in replacements:
        if old not in text:
            print(f"  WARNING: Expected text not found in {name}:")
            print(f"    {old[:80]}...")
            continue
        text = text.replace(old, new, 1)
    if text == original:
        print(f"  SKIP {name} (no changes)")
        return False
    page.save(text, summary=SUMMARY)
    print(f"  UPDATED {name}")
    return True


def main():
    site = connect()
    updated = 0

    # ── Introduction ──
    print("\n1. Introduction")
    updated += update_page(site, "Introduction", [
        (
            "'''DreamFactory is an open-source REST API platform that auto-generates secure, documented APIs for databases, files, and services.'''",
            f"'''{ANCHOR_SHORT}'''"
        ),
        (
            "DreamFactory is an open-source REST API platform that automatically generates secure, fully documented APIs for any data source in minutes. Whether you're connecting to databases, external services, or file systems, DreamFactory eliminates the need to write backend code.",
            f"{ANCHOR_LONG} Generate secure, fully documented REST APIs for any database, external service, or file system in minutes — without writing backend code."
        ),
    ])

    # ── Getting Started/Installing Dreamfactory ──
    print("\n2. Getting Started/Installing Dreamfactory")
    updated += update_page(site, "Getting Started/Installing Dreamfactory", [
        (
            "DreamFactory is a powerful open-source REST API platform that allows you to quickly build and deploy secure and scalable applications. Whether you are running Linux, Windows, or prefer using Docker, we've got you covered.",
            f"{ANCHOR_SHORT} Whether you are running Linux, Windows, or prefer using Docker, we've got you covered."
        ),
    ])

    # ── Architecture FAQ ──
    print("\n3. Architecture FAQ")
    updated += update_page(site, "Architecture FAQ", [
        (
            "DreamFactory is an open source REST API backend that provides RESTful services for building mobile, web, and IoT applications. In technical terms, DreamFactory is a runtime application that runs on a web server similar to a website running on a traditional LAMP server.",
            f"{ANCHOR_SHORT} In technical terms, DreamFactory is a runtime application that runs on a web server similar to a website running on a traditional LAMP server, exposing RESTful services for building enterprise, mobile, web, and IoT applications."
        ),
    ])

    # ── Introducing Rest Dreamfactory ──
    print("\n4. Introducing Rest Dreamfactory")
    updated += update_page(site, "Introducing Rest Dreamfactory", [
        (
            "This chapter introduces you to DreamFactory, an automated REST API generation, integration, and management platform. You can use DreamFactory to generate REST APIs for hundreds of data sources, including MySQL and Microsoft SQL Server databases, file systems including Amazon S3, and e-mail delivery providers like Mandrill. You can also integrate third-party APIs, including all of the services mentioned above. This opens up a whole new world of possibilities in terms of building sophisticated workflows. But before we jump into this introduction, some readers might be wondering what a REST API is in the first place, let alone why so many organizations rely on REST for their API implementations.",
            f"This chapter introduces you to DreamFactory. {ANCHOR_LONG} You can use DreamFactory to generate governed REST APIs for hundreds of data sources, including MySQL and Microsoft SQL Server databases, file systems including Amazon S3, and e-mail delivery providers like Mandrill. You can also integrate third-party APIs, including all of the services mentioned above. This opens up a whole new world of possibilities in terms of building sophisticated workflows. But before we jump into this introduction, some readers might be wondering what a REST API is in the first place, let alone why so many organizations rely on REST for their API implementations."
        ),
    ])

    # ── Security/Security Faq ──
    print("\n5. Security/Security Faq")
    updated += update_page(site, "Security/Security Faq", [
        # Overview paragraph (line 14)
        (
            "DreamFactory is an on-premise platform for instantly creating and managing APIs, currently used across the healthcare, finance, telecommunications, banking, government, & manufacturing industries. The platform is designed with security in mind to create APIs that maintain confidentiality of customer data, allow for restricted access based on administrator-defined privilege levels, and provide uninterrupted availability of the data.",
            f"{ANCHOR_LONG} DreamFactory is currently used across the healthcare, finance, telecommunications, banking, government, & manufacturing industries. The platform is designed with security in mind to create APIs that maintain confidentiality of customer data, allow for restricted access based on administrator-defined privilege levels, and provide uninterrupted availability of the data."
        ),
        # "What is the DreamFactory Platform?" bullet (line 22)
        (
            "* DreamFactory is an on-premise platform for instantly creating and managing APIs, currently used across the healthcare, finance, telecommunications, banking, government, & manufacturing industries.",
            f"* {ANCHOR_SHORT} DreamFactory is currently used across the healthcare, finance, telecommunications, banking, government, & manufacturing industries."
        ),
    ])

    # ── System Settings/01 System Api Brief ──
    print("\n6. System Settings/01 System Api Brief")
    updated += update_page(site, "System Settings/01 System Api Brief", [
        (
            "DreamFactory is a '''headless API platform''', meaning that everything you can do through the web-based administration console can also be accomplished programmatically through REST API calls.",
            f"DreamFactory is a '''headless enterprise data access platform''', meaning that everything you can do through the web-based administration console can also be accomplished programmatically through REST API calls."
        ),
    ])

    # ── GDPR API Gateway ──
    print("\n7. GDPR API Gateway")
    updated += update_page(site, "GDPR API Gateway", [
        # Section heading: keep but update description
        (
            "== API Automation Platform ==\n\nAs the name suggests, API Automation platforms automate the creation of APIs and provide a gateway for secure access to data endpoints. A full lifecycle platform combines API management, API generation, and API orchestration into a single runtime. Also referred to as Data Gateways, they provide discovery, access, and control mechanisms surrounding enterprise data that needs to be shared with external consumers. Ideally, a Data Gateway is non-disruptive to existing infrastructure - meaning that it can be retrofitted versus \"rip and replace\" approach.",
            "== Enterprise Data Access Platform ==\n\nEnterprise data access platforms provide governed API access to data endpoints, combining API generation, management, and orchestration into a single self-hosted runtime. Also referred to as Data Gateways, they provide discovery, access, and control mechanisms surrounding enterprise data that needs to be shared with external consumers and on-prem LLMs. Ideally, a Data Gateway is non-disruptive to existing infrastructure — meaning that it can be retrofitted versus a \"rip and replace\" approach."
        ),
        (
            "the DreamFactory API platform can help you bake in GDPR readiness into your infrastructure. DreamFactory's API platform is unique in that it is the only \"plug and play\" platform, automatically generating a data gateway for any data resource.",
            "the DreamFactory platform can help you bake in GDPR readiness into your infrastructure. DreamFactory is unique in that it is the only self-hosted enterprise data access platform that automatically generates a governed data gateway for any data resource."
        ),
        (
            "Progressive organizations are re-architecting their infrastructure with API platforms to get ahead of the competition. By taking this approach, enterprises have been able to share their data assets safely with any data consumer they need to support - whether to turbo charge new mobile and web app ecosystems, integrate cross-enterprise data, or create new business opportunities with partners & customers.\n\nNow, with GDPR, there is an emerging and mission critical consumer of enterprise data that an API platform can support: the Data Protection Officer.",
            "Progressive organizations are re-architecting their infrastructure with enterprise data access platforms to get ahead of the competition. By taking this approach, enterprises have been able to share their data assets safely with any data consumer they need to support — whether to turbo charge new mobile and web app ecosystems, integrate cross-enterprise data, enable on-prem LLMs, or create new business opportunities with partners & customers.\n\nNow, with GDPR, there is an emerging and mission critical consumer of enterprise data that a governed data access platform can support: the Data Protection Officer."
        ),
    ])

    # ── Sql Server ──
    print("\n8. Sql Server")
    updated += update_page(site, "Sql Server", [
        (
            "* Connect SQL Server and automatically generate REST API endpoints",
            "* Connect SQL Server and instantly generate governed REST API endpoints"
        ),
        (
            "'''When to use each:''' - '''DreamFactory''': When you need a comprehensive API management platform with security, governance, and multi-source support",
            "'''When to use each:''' - '''DreamFactory''': When you need a secure, self-hosted enterprise data access platform with governed API access, role-based access control, and multi-source support"
        ),
    ])

    print(f"\n{'='*50}")
    print(f"Done. Updated {updated}/8 pages.")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
