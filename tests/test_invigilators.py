import unittest

from app import assign_invigilators


class InvigilatorAssignmentTests(unittest.TestCase):
    def test_assigns_default_invigilators_by_hall_number(self):
        halls = [
            {'hall_number': 1, 'hall_name': 'Hall 1'},
            {'hall_number': 2, 'hall_name': 'Hall 2'},
            {'hall_number': 3, 'hall_name': 'Hall 3'},
        ]

        updated = assign_invigilators(halls)

        self.assertTrue(updated[0]['invigilator'])
        self.assertTrue(updated[1]['invigilator'])
        self.assertTrue(updated[2]['invigilator'])

    def test_assigns_room_based_faculty_and_rotates_across_generations(self):
        halls = [
            {'hall_number': 1, 'hall_name': 'A-202'},
            {'hall_number': 2, 'hall_name': 'B-103'},
        ]

        first = assign_invigilators(halls, rotation_seed=1, force=True)
        second = assign_invigilators(halls, rotation_seed=2, force=True)

        self.assertNotEqual(first[0]['invigilator'], second[0]['invigilator'])
        self.assertNotEqual(first[1]['invigilator'], second[1]['invigilator'])


if __name__ == '__main__':
    unittest.main()
