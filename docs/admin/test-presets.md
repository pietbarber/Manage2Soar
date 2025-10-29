# Managing Test Presets

This guide explains how to manage configurable test presets in the knowledge test system (Issue #135).

## Overview

Test presets define the number of questions from each category that should be included in knowledge tests. Instead of being hardcoded, these presets are now stored in the database and can be managed through the Django admin interface.

## Accessing Test Presets

1. Log in to the Django admin interface at `/admin/`
2. Navigate to **KNOWLEDGETEST** → **Test presets**
3. You'll see a list of all available test presets

## Default Presets

The system includes five migrated presets from the previous hardcoded implementation:

- **ASK21**: ASK-21 aircraft-specific test (73 questions)
- **PW5**: PW-5 aircraft-specific test (78 questions)  
- **DISCUS**: Discus aircraft-specific test (47 questions)
- **ACRO**: Aerobatics-focused test (30 questions)
- **EMPTY**: Blank preset for custom test creation

## Creating a New Preset

1. Click **"Add test preset"** in the admin interface
2. Fill in the required fields:
   - **Name**: Unique identifier for the preset (e.g., "DG-1000")
   - **Description**: Brief explanation of the preset's purpose
   - **Category weights**: JSON object defining question counts per category
   - **Is active**: Check to make the preset available in test creation
   - **Sort order**: Number determining display order (lower = first)

### Category Weights Format

The category weights field expects a JSON object where keys are category codes and values are question counts:

```json
{
  "GF": 10,
  "ST": 5,
  "WX": 4,
  "AIM": 5,
  "FAR": 5,
  "GFH": 10,
  "SSC": 5,
  "GNDOPS": 5,
  "ASK21": 19
}
```

Available category codes can be found in the QuestionCategory table.

## Editing Presets

1. Click on any preset name in the list to edit it
2. Modify fields as needed
3. Click **"Save"** or **"Save and continue editing"**

## Deleting Presets

⚠️ **Important**: Presets that are referenced by existing test templates cannot be deleted. The system will show an error message if you try to delete a protected preset.

To delete an unused preset:
1. Click on the preset name to edit it
2. Click the **"Delete"** button at the bottom left
3. Confirm the deletion

## Using Presets in Test Creation

Instructors can use presets when creating tests in two ways:

1. **Direct URL**: `/knowledgetest/create/?preset=ASK21`
2. **Form selection**: Presets appear as options in the test creation interface

When a preset is selected, the form fields are automatically populated with the preset's category weights.

## Troubleshooting

### Preset Not Appearing
- Check that **"Is active"** is enabled
- Verify the preset name doesn't contain special characters
- Ensure category codes in the weights match existing categories

### Deletion Error
- Check if any test templates reference the preset
- Consider deactivating instead of deleting if the preset might be needed later

### JSON Format Error
- Validate JSON syntax using an online JSON validator
- Ensure all category codes exist in the system
- Use integer values for question counts

## Technical Details

- Presets are stored in the `knowledgetest_testpreset` database table
- The `category_weights` field uses Django's JSONField for flexible storage
- The system maintains backward compatibility with the original hardcoded approach
- All presets are automatically migrated during the upgrade process