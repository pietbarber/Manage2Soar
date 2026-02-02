graph TD
    Start[Pilot with Power Rating Transitioning to Gliders] --> ReviewCheck{Is 14 CFR 61.56 Flight Review Current?}
    
    ReviewCheck -- Yes --> Endorsement[Receive 61.31(d)(2) Solo Endorsement]
    ReviewCheck -- No --> Choice{Choose Currency Path}

    subgraph "The WINGS Path (Recommended)"
    Choice -- "FAA WINGS Phase" --> WingsActivity[Complete 'APT-Glider Student Activity']
    WingsActivity --> WingsKnowledge[Complete 3 Knowledge Credits]
    WingsActivity --> WingsFlight[Complete 3 Flight Credits]
    WingsKnowledge --> PhaseComplete[WINGS Phase Completed]
    WingsFlight --> PhaseComplete
    PhaseComplete --> Exempt[Exempt from Flight Review per 61.56(e)]
    end

    subgraph "Standard Path"
    Choice -- "Traditional Review" --> StandardReview[1hr Ground + 1hr Flight/3 Flights]
    StandardReview --> ReviewLogbook[Instructor Signs 61.56 Review]
    end

    Exempt --> Endorsement
    ReviewLogbook --> Endorsement
    Endorsement --> Solo[Legal for PIC Glider Solo]

    style WingsActivity fill:#e1f5fe,stroke:#01579b
    style Exempt fill:#c8e6c9,stroke:#2e7d32
    style Endorsement fill:#fff9c4,stroke:#fbc02d
