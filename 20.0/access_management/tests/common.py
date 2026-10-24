from odoo.tests import new_test_user
from odoo.tests.common import TransactionCase


class AccessCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True, mail_notify_force_send=False))
        cls.team = cls.env['res.groups'].create({'name': 'AM test team'})
        groups = 'base.group_user,base.group_partner_manager,base.group_allow_export'
        cls.alice = new_test_user(cls.env, 'am_alice', groups=groups, name='Alice', password='am_alice_pw',
                                  email='alice@example.com')
        cls.alice.group_ids |= cls.team
        cls.bob = new_test_user(cls.env, 'am_bob', groups=groups, name='Bob', password='am_bob_pw',
                                email='bob@example.com')
        Partner = cls.env['res.partner']
        cls.bristol = Partner.create({'name': 'Bristol Ltd', 'city': 'Bristol', 'phone': '+44 7700 900123',
                                      'email': 'contact@bristol.example.com', 'ref': 'BR1'})
        cls.bath = Partner.create({'name': 'Bath Co', 'city': 'Bath', 'phone': '+44 7700 900456',
                                   'email': 'hello@bath.example.com'})
        cls.partner_model = cls.env['ir.model']._get('res.partner')

    def make_rule(self, users=None, **vals):
        vals.setdefault('name', 'Test rule')
        if users is not None:
            vals['user_ids'] = [(6, 0, users.ids)]
        elif 'group_ids' not in vals:
            vals['user_ids'] = [(6, 0, self.alice.ids)]
        return self.env['access.rule'].create(vals)

    def model_line(self, model='res.partner', **flags):
        return (0, 0, {'model_id': self.env['ir.model']._get(model).id, **flags})

    def field_line(self, field, mode, model='res.partner', **vals):
        return (0, 0, {'model_id': self.env['ir.model']._get(model).id,
                       'field_id': self.env['ir.model.fields']._get(model, field).id, 'mode': mode, **vals})

    def as_alice(self, model='res.partner'):
        return self.env[model].with_user(self.alice)

    def as_bob(self, model='res.partner'):
        return self.env[model].with_user(self.bob)
