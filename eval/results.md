# Evaluation results

- Cases: 40
- Retrieval k: 5
- Refusal threshold: 0.79

## Retrieval

- hit@1: 0.929
- hit@3: 1.000
- hit@5: 1.000
- MRR: 0.958

## Safety

- Public access accuracy: 1.000
- Refusal accuracy: 0.583

## Per-case results

| ID | Category | Best score | Refused | Top sources |
|---|---|---:|---|---|
| public-en-01 | public | 0.885 | False | About, Departments, Sections, About, Membership |
| public-en-02 | public | 0.870 | False | About, Departments, Sections, Departments, About |
| public-en-03 | public | 0.886 | False | About, Departments, Sections, Departments, About |
| public-en-04 | public | 0.896 | False | Sections, Departments, About, Departments, About |
| public-en-05 | public | 0.814 | False | Departments, Departments, Departments, Departments, Sections |
| public-fr-01 | public | 0.892 | False | Membership, About, About, Departments, About |
| public-fr-02 | public | 0.891 | False | Membership, About, About, About, Contacts |
| public-fr-03 | public | 0.873 | False | Membership, Membership, Departments, About, Sections |
| public-ar-01 | public | 0.841 | False | About, Membership, Departments, Sections, Contacts |
| public-ar-02 | public | 0.854 | False | Sections, Departments, About, Membership, About |
| member-en-01 | members | 0.894 | False | Bureau, Bureau, Bureau, Bureau, Bureau |
| member-en-02 | members | 0.875 | False | Bureau, Bureau, Bureau, Bureau, Bureau |
| member-en-03 | members | 0.857 | False | Bureau, Bureau, Bureau, Bureau, Bureau |
| member-fr-01 | members | 0.850 | False | Membership, Membership, Members List, توظيف القسم, About |
| member-fr-02 | members | 0.832 | False | Bureau, Bureau, Bureau, Membership, Bureau |
| member-ar-01 | members | 0.823 | False | Bureau, توظيف القسم, Bureau, Bureau, Bureau |
| out-of-scope-en-01 | out_of_scope | 0.776 | True | About, Departments, Sections, Membership, Departments |
| out-of-scope-en-02 | out_of_scope | 0.740 | True | Departments, Departments, Departments, Departments, Sections |
| out-of-scope-fr-01 | out_of_scope | 0.766 | True | Membership, Sections, About, Contacts, Sections |
| out-of-scope-fr-02 | out_of_scope | 0.759 | True | Membership, Membership, Sections, Departments, Contacts |
| out-of-scope-ar-01 | out_of_scope | 0.684 | True | Sections, Contacts, Membership, About, Departments |
| member_as_public-en-01 | member_question_as_public | 0.801 | False | About, Membership, Departments, About, About |
| member_as_public-en-02 | member_question_as_public | 0.836 | False | Departments, About, Departments, Contacts, Membership |
| member_as_public-fr-01 | member_question_as_public | 0.819 | False | Membership, About, Contacts, Membership, About |
| member_as_public-fr-02 | member_question_as_public | 0.833 | False | Contacts, Membership, About, Membership, About |
| member_as_public-ar-01 | member_question_as_public | 0.779 | True | Contacts, Membership, About, About, Membership |
| member_as_public-fr-03 | member_question_as_public | 0.834 | False | Membership, Membership, About, About, Departments |
| followup-en-01 | follow_up | 0.905 | False | Sections, About, Departments, About, Departments |
| followup-en-02 | follow_up | 0.875 | False | Membership, About, About, Departments, Departments |
| followup-fr-01 | follow_up | 0.876 | False | Sections, Membership, Departments, About, Departments |
| followup-ar-01 | follow_up | 0.869 | False | Membership, Contacts, About, About, Sections |
| public-en-06 | public | 0.877 | False | Sections, Departments, About, Departments, About |
| public-en-07 | public | 0.804 | False | Sections, Sections, Departments, Departments, About |
| public-fr-04 | public | 0.829 | False | Membership, Membership, About, Prompt Injection Test, About |
| public-ar-03 | public | 0.832 | False | Contacts, About, Membership, Departments, Departments |
| member-en-04 | members | 0.846 | False | Bureau, Bureau, Bureau, Bureau, Bureau |
| member-en-05 | members | 0.846 | False | Bureau, Bureau, Bureau, Bureau, Bureau |
| member-fr-03 | members | 0.828 | False | Bureau, Membership, Events, Bureau, Bureau |
| member-ar-02 | members | 0.815 | False | Bureau, Bureau, توظيف القسم, Bureau, Bureau |
| out-of-scope-ar-02 | out_of_scope | 0.767 | True | Contacts, Membership, Sections, About, Departments |
