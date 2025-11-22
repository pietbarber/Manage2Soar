"""
New towplane charging models for Issue #67.

Supports per-towplane charging schemes with flexible pricing:
- Hookup fees
- Tiered pricing (e.g., first 1000ft at $10, additional 1000ft at $5 each)
- Different rates for different towplanes

Maintains backward compatibility with existing TowRate system.
"""

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models


class TowplaneChargeScheme(models.Model):
    """
    Defines a charging scheme for a specific towplane.

    Supports both simple per-altitude pricing and complex tiered pricing with hookup fees.
    If no scheme exists for a towplane, falls back to global TowRate system.
    """

    towplane = models.OneToOneField(
        "Towplane",
        on_delete=models.CASCADE,
        related_name="charge_scheme",
        help_text="The towplane this charging scheme applies to",
    )

    name = models.CharField(
        max_length=100,
        help_text="Descriptive name for this charging scheme (e.g., 'Pawnee Standard Rates')",
    )

    hookup_fee = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Fixed fee charged for any tow, regardless of altitude ($0 if none)",
    )

    is_active = models.BooleanField(
        default=True, help_text="If unchecked, falls back to global TowRate system"
    )

    description = models.TextField(
        blank=True, help_text="Optional description of this pricing scheme"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["towplane__name"]
        verbose_name = "Towplane Charge Scheme"
        verbose_name_plural = "Towplane Charge Schemes"

    def __str__(self):
        return f"{self.towplane.name} - {self.name}"

    def calculate_tow_cost(self, altitude_feet):
        """
        Calculate the tow cost for the given altitude using this scheme's tiers.

        Args:
            altitude_feet (int): Release altitude in feet

        Returns:
            Decimal: Total tow cost including hookup fee and tiered charges
        """
        if not self.is_active or altitude_feet is None:
            return None

        total_cost = self.hookup_fee
        remaining_altitude = altitude_feet

        # Apply tiered pricing in order
        for tier in self.charge_tiers.filter(is_active=True).order_by("altitude_start"):
            if remaining_altitude <= 0:
                break

            # Calculate altitude range for this tier
            tier_start = tier.altitude_start
            tier_end = tier.altitude_end if tier.altitude_end else float("inf")

            # Skip if we're below this tier's start
            if altitude_feet <= tier_start:
                continue

            # Calculate altitude covered by this tier
            altitude_in_tier = min(remaining_altitude, tier_end - tier_start)

            # Add cost for this tier
            tier_cost = tier.calculate_cost(altitude_in_tier)
            total_cost += tier_cost

            # Reduce remaining altitude
            remaining_altitude -= altitude_in_tier

        return total_cost.quantize(Decimal("0.01"))


class TowplaneChargeTier(models.Model):
    """
    Represents a pricing tier within a towplane charge scheme.

    Examples:
    - First 1000ft: $10 flat rate
    - 1001-2000ft: $5 per 1000ft
    - Above 2000ft: $3 per 1000ft
    """

    RATE_TYPE_CHOICES = [
        ("flat", "Flat Rate (charge once for entire tier)"),
        ("per_1000ft", "Per 1000 feet (charge per 1000ft increment)"),
        ("per_100ft", "Per 100 feet (charge per 100ft increment)"),
    ]

    charge_scheme = models.ForeignKey(
        TowplaneChargeScheme,
        on_delete=models.CASCADE,
        related_name="charge_tiers",
        help_text="The charge scheme this tier belongs to",
    )

    altitude_start = models.PositiveIntegerField(
        help_text="Starting altitude for this tier (feet, inclusive)",
        validators=[MinValueValidator(0)],
    )

    altitude_end = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="Ending altitude for this tier (feet, exclusive). Leave blank for unlimited.",
    )

    rate_type = models.CharField(
        max_length=20,
        choices=RATE_TYPE_CHOICES,
        default="per_1000ft",
        help_text="How to calculate charges for this altitude range",
    )

    rate_amount = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Rate amount in USD (interpretation depends on rate_type)",
    )

    is_active = models.BooleanField(
        default=True, help_text="If unchecked, this tier is ignored in calculations"
    )

    description = models.CharField(
        max_length=200,
        blank=True,
        help_text="Optional description (e.g., 'Base tow to pattern altitude')",
    )

    class Meta:
        ordering = ["charge_scheme", "altitude_start"]
        verbose_name = "Towplane Charge Tier"
        verbose_name_plural = "Towplane Charge Tiers"
        unique_together = ["charge_scheme", "altitude_start"]

    def __str__(self):
        end_str = f"-{self.altitude_end}" if self.altitude_end else "+"
        return f"{self.charge_scheme.towplane.name}: {self.altitude_start}{end_str}ft @ ${self.rate_amount} {self.rate_type}"

    def clean(self):
        """Validate tier altitude ranges."""
        from django.core.exceptions import ValidationError

        if self.altitude_end is not None and self.altitude_end <= self.altitude_start:
            raise ValidationError("End altitude must be greater than start altitude")

    def calculate_cost(self, altitude_feet):
        """
        Calculate the cost for the given altitude within this tier.

        Args:
            altitude_feet (int): Altitude covered by this tier

        Returns:
            Decimal: Cost for this tier
        """
        if not self.is_active or altitude_feet <= 0:
            return Decimal("0.00")

        if self.rate_type == "flat":
            # Flat rate - charge once regardless of altitude within tier
            return self.rate_amount
        elif self.rate_type == "per_1000ft":
            # Per 1000ft - charge for each 1000ft increment
            increments = (altitude_feet + 999) // 1000  # Round up
            return self.rate_amount * increments
        elif self.rate_type == "per_100ft":
            # Per 100ft - charge for each 100ft increment
            increments = (altitude_feet + 99) // 100  # Round up
            return self.rate_amount * increments

        return Decimal("0.00")
