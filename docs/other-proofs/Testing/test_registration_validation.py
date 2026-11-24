import pytest
from app.registration import validate_patient_registration

@pytest.mark.parametrize('email',['missing-domain@','@missing-name.com','a b@test.com','a@@test.com'])
def test_rejects_malformed_email(email):
    with pytest.raises(ValueError): validate_patient_registration('Patient',email,'ValidPass123!')

@pytest.mark.parametrize('password',[' '*8,'short','x'*129])
def test_rejects_unusable_password(password):
    with pytest.raises(ValueError): validate_patient_registration('Patient','patient@test.com',password)

def test_normalizes_name_and_email_without_changing_password():
    assert validate_patient_registration(' Patient Name ',' PATIENT@Test.com ',' ValidPass123! ') == ('Patient Name','patient@test.com',' ValidPass123! ')
