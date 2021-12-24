from openfisca_uk.model_api import *


class income_support_reported(Variable):
    value_type = float
    entity = Person
    label = u"Income Support (reported amount)"
    definition_period = YEAR


class would_claim_IS(Variable):
    value_type = bool
    entity = BenUnit
    label = u"Would claim Income Support"
    documentation = (
        "Whether this family would claim Income Support if eligible"
    )
    definition_period = YEAR

    def formula(benunit, period, parameters):
        return (
            random(benunit) <= parameters(period).benefit.income_support.takeup
        ) + benunit("claims_all_entitled_benefits", period)


class claims_IS(Variable):
    value_type = bool
    entity = BenUnit
    label = u"Whether this family is imputed to claim Income Support"
    definition_period = YEAR

    def formula(benunit, period, parameters):
        return benunit("would_claim_IS", period) & benunit(
            "claims_legacy_benefits", period
        )


class income_support_applicable_income(Variable):
    value_type = float
    entity = BenUnit
    label = u"Relevant income for Income Support means test"
    definition_period = YEAR

    def formula(benunit, period, parameters):
        IS = parameters(period).benefit.income_support
        INCOME_COMPONENTS = [
            "employment_income",
            "self_employment_income",
            "property_income",
            "pension_income",
        ]
        income = aggr(benunit, period, INCOME_COMPONENTS)
        tax = aggr(
            benunit,
            period,
            ["income_tax", "national_insurance"],
        )
        income += aggr(benunit, period, ["social_security_income"])
        income -= tax
        income -= aggr(benunit, period, ["pension_contributions"]) * 0.5
        family_type = benunit("family_type", period)
        families = family_type.possible_values
        # Calculate income disregards for each family type.
        mt = IS.means_test
        single = family_type == families.SINGLE
        income_disregard_single = single * mt.income_disregard_single
        single = family_type == families.SINGLE
        income_disregard_couple = (
            benunit("is_couple", period) * mt.income_disregard_couple
        )
        lone_parent = family_type == families.LONE_PARENT
        income_disregard_lone_parent = (
            lone_parent * mt.income_disregard_lone_parent
        )
        income_disregard = (
            income_disregard_single
            + income_disregard_couple
            + income_disregard_lone_parent
        ) * WEEKS_IN_YEAR
        return max_(0, income - income_disregard)


class income_support_eligible(Variable):
    value_type = bool
    entity = BenUnit
    label = u"Whether eligible for Income Support"
    definition_period = YEAR

    def formula(benunit, period, parameters):
        youngest_child_5_or_under = benunit("youngest_child_age", period) <= 5
        lone_parent = benunit("is_lone_parent", period)
        lone_parent_with_young_child = lone_parent & youngest_child_5_or_under
        QUALIFYING_COMPONENTS = ["is_carer_for_benefits"]
        eligible = (
            aggr(benunit, period, QUALIFYING_COMPONENTS) > 0
        ) | lone_parent_with_young_child
        under_SP_age = benunit.any(benunit.members("is_SP_age", period)) == 0
        eligible *= under_SP_age
        return not_(benunit("ESA_income", period) > 0) & eligible


class income_support_applicable_amount(Variable):
    value_type = float
    entity = BenUnit
    label = u"Applicable amount of Income Support"
    definition_period = YEAR

    def formula(benunit, period, parameters):
        IS = parameters(period).benefit.income_support
        amounts = IS.amounts
        younger_age = benunit("youngest_adult_age", period)
        older_age = benunit("eldest_adult_age", period)
        children = benunit.sum(benunit.members("is_child", period)) > 0
        single = benunit("is_single", period)
        single_under_25 = single * not_(children) * (younger_age < 25)
        single_over_25 = single * not_(children) * (younger_age >= 25)
        lone_young = single * children * (younger_age < 18)
        lone_old = single * children * (younger_age >= 18)
        couple_young = not_(single) * (older_age < 18)
        couple_mixed = not_(single) * (older_age >= 18) * (younger_age < 18)
        couple_old = not_(single) * (younger_age >= 18)
        personal_allowance = (
            select(
                [
                    single_under_25,
                    single_over_25,
                    lone_young,
                    lone_old,
                    couple_young,
                    couple_mixed,
                    couple_old,
                ],
                [
                    amounts.amount_16_24,
                    amounts.amount_over_25,
                    amounts.amount_lone_16_17,
                    amounts.amount_lone_over_18,
                    amounts.amount_couples_16_17,
                    amounts.amount_couples_age_gap,
                    amounts.amount_couples_over_18,
                ],
            )
            * WEEKS_IN_YEAR
        )
        premiums = benunit("benefits_premiums", period)
        return (
            (personal_allowance + premiums)
            * benunit("income_support_eligible", period)
            * benunit("claims_IS", period)
        )


class income_support(Variable):
    value_type = float
    entity = BenUnit
    label = u"Income Support"
    definition_period = YEAR

    def formula(benunit, period, parameters):
        amount = benunit("income_support_applicable_amount", period)
        income = benunit("income_support_applicable_income", period)
        return max_(0, amount - income)
