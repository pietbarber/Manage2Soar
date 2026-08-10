# Test: Verify the offline modal helper extraction works correctly


def main():
    # Simulate finding duplicates in the HTML file
    with open(
        "/home/pb/Projects/Manage2Soar/logsheet/templates/logsheet/logsheet_manage.html",
        "r",
    ) as f:
        content = f.read()

    # Count occurrences of the duplicate text
    count = content.count(
        "No cached data available for offline entry. Please connect to the internet at least once to cache flight data."
    )
    print(f"Found {count} occurrences of the duplicated modal HTML")

    if count > 1:
        print("DUPLICATE DETECTED - helper function needed!")
        return False
    else:
        print("All good - only one occurrence (in helper function)")
        return True


if __name__ == "__main__":
    main()
