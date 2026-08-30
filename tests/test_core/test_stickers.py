from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from ksicht.core import models
from ksicht.core.stickers import resolvers


pytestmark = [pytest.mark.django_db]

tid1 = str(uuid4())
tid2 = str(uuid4())
tid3 = str(uuid4())
tid4 = str(uuid4())

s1 = models.GradeSeries(
    id=1, series="1", submission_deadline=datetime(2020, 1, 1, 0, 0)
)
s2 = models.GradeSeries(
    id=2, series="2", submission_deadline=datetime(2020, 3, 1, 0, 0)
)

p1 = models.Participant(user_id="1")
p2 = models.Participant(user_id="2")
p3 = models.Participant(user_id="3")
p4 = models.Participant(user_id="4")
p5 = models.Participant(user_id="5")

a1 = models.GradeApplication(id="1", participant_id="1")
a2 = models.GradeApplication(id="2", participant_id="2")
a3 = models.GradeApplication(id="3", participant_id="3")
a4 = models.GradeApplication(id="4", participant_id="4")
a5 = models.GradeApplication(id="5", participant_id="5")

t1 = models.Task(id=tid1, points=Decimal("10.00"))
t2 = models.Task(id=tid2, points=Decimal("10.00"))
t3 = models.Task(id=tid3, points=Decimal("10.00"))
t4 = models.Task(id=tid4, points=Decimal("10.00"))

sub1 = models.TaskSolutionSubmission(task_id=tid1)
sub2 = models.TaskSolutionSubmission(task_id=tid2)
sub3 = models.TaskSolutionSubmission(task_id=tid3)
sub4 = models.TaskSolutionSubmission(task_id=tid4)


@pytest.mark.parametrize(
    "context, result",
    (
        (
            {
                "current": {
                    "series": s1,
                    "grade": {
                        "tasks": {
                            s1: (t1, t2, t3),
                            s2: (t4,),
                        },
                    },
                    "participant": {
                        "submissions": {
                            "by_series": {
                                s1: (sub1, sub2, sub3),
                                s2: (),
                            }
                        },
                    },
                },
            },
            True,
        ),
        (
            {
                "current": {
                    "series": s2,
                    "grade": {
                        "tasks": {
                            s1: (t1, t2, t3),
                            s2: (t4,),
                        },
                    },
                    "participant": {
                        "submissions": {
                            "by_series": {
                                s1: (),
                                s2: (sub4,),
                            }
                        },
                    },
                },
            },
            True,
        ),
        (
            {
                "current": {
                    "series": s1,
                    "grade": {
                        "tasks": {
                            s1: (t1, t2, t3),
                            s2: (t4,),
                        },
                    },
                    "participant": {
                        "submissions": {
                            "by_series": {
                                s1: (),
                                s2: (),
                            }
                        },
                    },
                },
            },
            False,
        ),
        (
            {
                "current": {
                    "series": s1,
                    "grade": {
                        "tasks": {
                            s1: (),
                            s2: (),
                        },
                    },
                    "participant": {
                        "submissions": {
                            "by_series": {
                                s1: (),
                                s2: (),
                            },
                        },
                    },
                },
            },
            False,
        ),
    ),
)
def test_solved_all_tasks_in_series(context, result):
    assert resolvers.solved_all_tasks_in_series(context) is result


@pytest.mark.parametrize(
    "context, result",
    (
        (
            {
                "current": {
                    "is_last_series": True,
                    "participant": {
                        "submissions": {
                            "by_series": {
                                s1: (sub1,),
                                s2: (sub2,),
                            }
                        },
                    },
                },
            },
            True,
        ),
        (
            {
                "current": {
                    "is_last_series": False,
                    "participant": {
                        "submissions": {
                            "by_series": {
                                s1: (sub1,),
                                s2: (sub2,),
                            }
                        },
                    },
                },
            },
            False,
        ),
        (
            {
                "current": {
                    "is_last_series": True,
                    "participant": {
                        "submissions": {
                            "by_series": {
                                s1: (),
                                s2: (sub1,),
                            }
                        },
                    },
                },
            },
            False,
        ),
        (
            {
                "current": {
                    "is_last_series": True,
                    "participant": {
                        "submissions": {
                            "by_series": {
                                s1: (),
                                s2: (),
                            }
                        },
                    },
                }
            },
            False,
        ),
    ),
)
def test_solution_in_every_series(context, result):
    assert resolvers.solution_in_every_series(context) is result


@pytest.mark.parametrize(
    "context, result",
    (
        (
            {
                "current": {
                    "is_last_series": True,
                    "participant": {"submissions": {"by_tasks": {t1: sub1, t1: sub2}}},
                },
            },
            True,
        ),
        (
            {
                "current": {
                    "is_last_series": False,
                    "participant": {
                        "submissions": {"by_tasks": {t1: sub1, t1: sub2}},
                    },
                },
            },
            False,
        ),
        (
            {
                "current": {
                    "is_last_series": True,
                    "participant": {"submissions": {"by_tasks": {t1: None, t2: sub1}}},
                },
            },
            False,
        ),
        (
            {
                "current": {
                    "is_last_series": True,
                    "participant": {"submissions": {"by_tasks": {t1: None, t2: None}}},
                },
            },
            False,
        ),
    ),
)
def test_solved_all_tasks(context, result):
    assert resolvers.solved_all_tasks(context) is result


@pytest.mark.parametrize(
    "context, result",
    (
        (
            {
                "current": {
                    "series": s1,
                    "participant": {
                        "submissions": {
                            "by_series": {
                                s1: (),
                                s2: (
                                    models.TaskSolutionSubmission(
                                        score=Decimal("10.0")
                                    ),
                                    models.TaskSolutionSubmission(score=Decimal("5.0")),
                                    models.TaskSolutionSubmission(score=Decimal("0.1")),
                                ),
                            }
                        },
                    },
                },
            },
            False,
        ),
        (
            {
                "current": {
                    "series": s2,
                    "participant": {
                        "submissions": {
                            "by_series": {
                                s1: (),
                                s2: (
                                    models.TaskSolutionSubmission(
                                        score=Decimal("10.0")
                                    ),
                                    models.TaskSolutionSubmission(score=Decimal("5.0")),
                                    models.TaskSolutionSubmission(score=Decimal("0.1")),
                                ),
                            }
                        },
                    },
                },
            },
            False,
        ),
        (
            {
                "current": {
                    "series": s1,
                    "participant": {
                        "submissions": {
                            "by_series": {
                                s1: (
                                    models.TaskSolutionSubmission(score=Decimal("0.0")),
                                    models.TaskSolutionSubmission(score=Decimal("0.1")),
                                ),
                                s2: (),
                            }
                        },
                    },
                },
            },
            True,
        ),
        (
            {
                "current": {
                    "series": s2,
                    "participant": {
                        "submissions": {
                            "by_series": {
                                s1: (
                                    models.TaskSolutionSubmission(score=Decimal("0.0")),
                                    models.TaskSolutionSubmission(score=Decimal("0.1")),
                                ),
                                s2: (),
                            }
                        },
                    },
                },
            },
            False,
        ),
    ),
)
def test_zero_points(context, result):
    assert resolvers.zero_points(context) is result


@pytest.mark.parametrize(
    "context, result",
    (
        (
            {
                "current": {
                    "participant": {
                        "submissions": {"all": ()},
                    },
                },
            },
            False,
        ),
        (
            {
                "current": {
                    "participant": {
                        "submissions": {
                            "all": (
                                models.TaskSolutionSubmission(score=Decimal("10.0")),
                                models.TaskSolutionSubmission(score=Decimal("5.0")),
                                models.TaskSolutionSubmission(score=Decimal("0.1")),
                            ),
                        },
                    },
                },
            },
            False,
        ),
        (
            {
                "current": {
                    "participant": {
                        "submissions": {
                            "all": (
                                models.TaskSolutionSubmission(score=Decimal("10.0")),
                                models.TaskSolutionSubmission(score=Decimal("5.0")),
                                models.TaskSolutionSubmission(score=None),
                            ),
                        },
                    },
                },
            },
            False,
        ),
        (
            {
                "current": {
                    "participant": {
                        "submissions": {
                            "all": (
                                models.TaskSolutionSubmission(score=Decimal("90.0")),
                                models.TaskSolutionSubmission(score=Decimal("50.0")),
                            ),
                        },
                    },
                },
            },
            True,
        ),
    ),
)
def test_reached_100(context, result):
    assert resolvers.reached_100(context) is result


@pytest.mark.parametrize(
    "context, result",
    (
        (
            {
                "current": {
                    "participant": {
                        "submissions": {"all": ()},
                    },
                },
            },
            False,
        ),
        (
            {
                "current": {
                    "participant": {
                        "submissions": {
                            "all": (
                                models.TaskSolutionSubmission(score=Decimal("10.0")),
                                models.TaskSolutionSubmission(score=Decimal("5.0")),
                                models.TaskSolutionSubmission(score=Decimal("0.1")),
                            ),
                        },
                    },
                },
            },
            False,
        ),
        (
            {
                "current": {
                    "participant": {
                        "submissions": {
                            "all": (
                                models.TaskSolutionSubmission(score=Decimal("90.0")),
                                models.TaskSolutionSubmission(score=Decimal("50.0")),
                            ),
                        },
                    },
                },
            },
            False,
        ),
        (
            {
                "current": {
                    "participant": {
                        "submissions": {
                            "all": (
                                models.TaskSolutionSubmission(score=Decimal("90.0")),
                                models.TaskSolutionSubmission(score=None),
                            ),
                        },
                    },
                },
            },
            False,
        ),
        (
            {
                "current": {
                    "participant": {
                        "submissions": {
                            "all": (
                                models.TaskSolutionSubmission(score=Decimal("90.0")),
                                models.TaskSolutionSubmission(score=Decimal("60.0")),
                            ),
                        },
                    },
                },
            },
            True,
        ),
    ),
)
def test_reached_150(context, result):
    assert resolvers.reached_150(context) is result


@pytest.mark.parametrize(
    "context, result",
    (
        (
            {
                "current": {
                    "participant": {
                        "submissions": {
                            "by_series": {
                                s1: (
                                    models.TaskSolutionSubmission(
                                        task=t1, score=Decimal("5.0")
                                    ),
                                    models.TaskSolutionSubmission(task=t2, score=None),
                                )
                            }
                        },
                    },
                    "series": s1,
                    "grade": {
                        "tasks": {
                            s1: (t1, t2),
                        }
                    },
                },
            },
            False,
        ),
        (
            {
                "current": {
                    "participant": {
                        "submissions": {
                            "by_series": {
                                s1: (
                                    models.TaskSolutionSubmission(
                                        task=t1, score=Decimal("10.0")
                                    ),
                                    models.TaskSolutionSubmission(task=t2, score=None),
                                ),
                                s2: (),
                            }
                        },
                    },
                    "series": s2,
                    "grade": {
                        "tasks": {
                            s1: (t1, t2),
                            s2: (),
                        }
                    },
                }
            },
            False,
        ),
        (
            {
                "current": {
                    "participant": {
                        "submissions": {
                            "by_series": {
                                s1: (
                                    models.TaskSolutionSubmission(
                                        task=t1, score=Decimal("10.0")
                                    ),
                                    models.TaskSolutionSubmission(task=t2, score=None),
                                )
                            }
                        },
                    },
                    "series": s1,
                    "grade": {
                        "tasks": {
                            s1: (t1, t2),
                        }
                    },
                },
            },
            True,
        ),
        (
            {
                "current": {
                    "participant": {
                        "submissions": {
                            "by_series": {
                                s1: (
                                    models.TaskSolutionSubmission(task=t1, score=None),
                                    models.TaskSolutionSubmission(
                                        task=t2, score=Decimal("10.0")
                                    ),
                                )
                            }
                        },
                    },
                    "series": s1,
                    "grade": {
                        "tasks": {
                            s1: (t1, t2),
                        }
                    },
                },
            },
            True,
        ),
        (
            {
                "current": {
                    "participant": {
                        "submissions": {
                            "by_series": {
                                s1: (
                                    models.TaskSolutionSubmission(
                                        task=t1, score=Decimal("10.0")
                                    ),
                                    models.TaskSolutionSubmission(
                                        task=t2, score=Decimal("10.0")
                                    ),
                                )
                            }
                        },
                    },
                    "series": s1,
                    "grade": {
                        "tasks": {
                            s1: (t1, t2),
                        }
                    },
                }
            },
            True,
        ),
    ),
)
def test_full_score(context, result):
    assert resolvers.full_score(context) is result


@pytest.mark.parametrize(
    "context, result",
    (
        (
            {
                "participant": p1,
                "current": {
                    "series": s1,
                    "grade": {
                        "by_participant": {
                            p1: {},
                            p2: {},
                            p3: {},
                            p4: {},
                            p5: {},
                        }
                    },
                },
            },
            True,
        ),
        (
            {
                "participant": p2,
                "current": {
                    "series": s1,
                    "grade": {
                        "by_participant": {
                            p1: {},
                            p2: {},
                            p3: {},
                            p4: {},
                            p5: {},
                        }
                    },
                },
            },
            False,
        ),
        (
            {
                "participant": p3,
                "current": {
                    "series": s1,
                    "grade": {
                        "by_participant": {
                            p1: {},
                            p2: {},
                            p3: {},
                            p4: {},
                            p5: {},
                        }
                    },
                },
            },
            False,
        ),
        (
            {
                "participant": p4,
                "current": {
                    "series": s1,
                    "grade": {
                        "by_participant": {
                            p1: {},
                            p2: {},
                            p3: {},
                            p4: {},
                            p5: {},
                        }
                    },
                },
            },
            False,
        ),
        (
            {
                "participant": p5,
                "current": {
                    "series": s1,
                    "grade": {
                        "by_participant": {
                            p1: {},
                            p2: {},
                            p3: {},
                            p4: {},
                            p5: {},
                        }
                    },
                },
            },
            False,
        ),
        (
            {
                "participant": p1,
                "current": {
                    "series": s2,
                    "grade": {
                        "by_participant": {
                            p1: {},
                            p2: {},
                            p3: {},
                            p4: {},
                            p5: {},
                        }
                    },
                },
            },
            False,
        ),
        (
            {
                "participant": p2,
                "current": {
                    "series": s2,
                    "grade": {
                        "by_participant": {
                            p1: {},
                            p2: {},
                            p3: {},
                            p4: {},
                            p5: {},
                        }
                    },
                },
            },
            False,
        ),
        (
            {
                "participant": p3,
                "current": {
                    "series": s2,
                    "grade": {
                        "by_participant": {
                            p1: {},
                            p2: {},
                            p3: {},
                            p4: {},
                            p5: {},
                        }
                    },
                },
            },
            False,
        ),
        (
            {
                "participant": p4,
                "current": {
                    "series": s2,
                    "grade": {
                        "by_participant": {
                            p1: {},
                            p2: {},
                            p3: {},
                            p4: {},
                            p5: {},
                        }
                    },
                },
            },
            False,
        ),
        (
            {
                "participant": p5,
                "current": {
                    "series": s2,
                    "grade": {
                        "by_participant": {
                            p1: {},
                            p2: {},
                            p3: {},
                            p4: {},
                            p5: {},
                        }
                    },
                },
            },
            True,
        ),
    ),
)
def test_random_2_percent(context, result):
    assert resolvers.random_2_percent(context) is result


@pytest.mark.parametrize(
    "context, result",
    (
        # p1 submitted digitally within 30 minutes of deadline → eligible
        (
            {
                "participant": p1,
                "current": {
                    "series": s1,
                    "grade": {
                        "by_participant": {
                            p1: {
                                "submissions": {
                                    "by_series": {
                                        s1: (
                                            models.TaskSolutionSubmission(
                                                submitted_at=datetime(2019, 12, 10),
                                                file="foo.pdf",
                                            ),
                                            models.TaskSolutionSubmission(
                                                submitted_at=datetime(2019, 12, 31, 23, 45),
                                                file="foo.pdf",
                                            ),
                                        ),
                                    },
                                },
                            },
                        },
                    },
                },
            },
            True,
        ),
        # p1 submitted but file=None → not eligible
        (
            {
                "participant": p1,
                "current": {
                    "series": s1,
                    "grade": {
                        "by_participant": {
                            p1: {
                                "submissions": {
                                    "by_series": {
                                        s1: (
                                            models.TaskSolutionSubmission(
                                                submitted_at=datetime(2019, 12, 31, 23, 45),
                                                file=None,
                                            ),
                                        ),
                                    },
                                },
                            },
                        },
                    },
                },
            },
            False,
        ),
        # p1 submitted more than 30 min before deadline → not eligible
        (
            {
                "participant": p1,
                "current": {
                    "series": s1,
                    "grade": {
                        "by_participant": {
                            p1: {
                                "submissions": {
                                    "by_series": {
                                        s1: (
                                            models.TaskSolutionSubmission(
                                                submitted_at=datetime(2019, 12, 31, 19, 59),
                                                file="foo.pdf",
                                            ),
                                        ),
                                    },
                                },
                            },
                        },
                    },
                },
            },
            False,
        ),
        # p1 is NOT among top 10 latest (11 other participants submitted later)
        (
            {
                "participant": p1,
                "current": {
                    "series": s1,
                    "grade": {
                        "by_participant": {
                            **{
                                models.Participant(user_id=str(i)): {
                                    "submissions": {
                                        "by_series": {
                                            s1: (
                                                models.TaskSolutionSubmission(
                                                    submitted_at=datetime(
                                                        2019, 12, 31, 23, 50
                                                    ),
                                                    file="bar.pdf",
                                                ),
                                            ),
                                        },
                                    },
                                }
                                for i in range(100, 111)
                            },
                            p1: {
                                "submissions": {
                                    "by_series": {
                                        s1: (
                                            models.TaskSolutionSubmission(
                                                submitted_at=datetime(
                                                    2019, 12, 31, 23, 35
                                                ),
                                                file="foo.pdf",
                                            ),
                                        ),
                                    },
                                },
                            },
                        },
                    },
                },
            },
            False,
        ),
    ),
)
def test_late_submission(context, result):
    assert resolvers.late_submission(context) is result


@pytest.mark.parametrize(
    "context, result",
    (
        (
            {
                "current": {
                    "series": s1,
                    "participant": {
                        "submissions": {
                            "by_series": {
                                s1: (
                                    models.TaskSolutionSubmission(
                                        submitted_at=datetime(2019, 12, 1)
                                    ),
                                    models.TaskSolutionSubmission(
                                        submitted_at=datetime(2019, 12, 13, 23)
                                    ),
                                )
                            }
                        },
                    },
                },
            },
            True,
        ),
        (
            {
                "current": {
                    "series": s1,
                    "participant": {
                        "submissions": {"by_series": {s1: ()}},
                    },
                },
            },
            False,
        ),
        (
            {
                "current": {
                    "series": s1,
                    "participant": {
                        "submissions": {
                            "by_series": {
                                s1: (
                                    models.TaskSolutionSubmission(
                                        submitted_at=datetime(2019, 12, 10)
                                    ),
                                    models.TaskSolutionSubmission(
                                        submitted_at=datetime(2019, 12, 31, 19, 59)
                                    ),
                                )
                            }
                        },
                    },
                },
            },
            False,
        ),
    ),
)
def test_early_submission(context, result):
    assert resolvers.early_submission(context) is result


@pytest.mark.parametrize(
    "context, result",
    (
        (
            {
                "current": {
                    "is_last_series": False,
                    "participant": {
                        "series": {
                            s1: {
                                "rank": 1,
                            },
                            s2: {
                                "rank": 1,
                            },
                        },
                    },
                },
            },
            False,
        ),
        (
            {
                "current": {
                    "is_last_series": True,
                    "participant": {
                        "series": {
                            s1: {
                                "rank": 1,
                            },
                            s2: {
                                "rank": 1,
                            },
                        },
                    },
                },
            },
            True,
        ),
        (
            {
                "current": {
                    "is_last_series": True,
                    "participant": {
                        "series": {
                            s1: {
                                "rank": 8,
                            },
                            s2: {
                                "rank": 1,
                            },
                        },
                    },
                },
            },
            False,
        ),
        (
            {
                "current": {
                    "is_last_series": True,
                    "participant": {
                        "series": {
                            s1: {
                                "rank": 7,
                            },
                            s2: {
                                "rank": 7,
                            },
                        },
                    },
                },
            },
            True,
        ),
    ),
)
def test_ranked_no_worse_than_7th(context, result):
    assert resolvers.ranked_no_worse_than_7th(context) is result


@pytest.mark.parametrize(
    "context, result",
    (
        (
            {
                "current": {
                    "series": s1,
                    "participant": {
                        "series": {
                            s1: {
                                "rank": 1,
                            },
                        },
                    },
                },
            },
            False,
        ),
        (
            {
                "current": {
                    "series": s1,
                    "participant": {
                        "series": {
                            s1: {
                                "rank": 42,
                            },
                        },
                    },
                },
            },
            True,
        ),
        (
            {
                "current": {
                    "series": s1,
                    "participant": {
                        "series": {
                            s1: {
                                "rank": 43,
                            },
                        },
                    },
                },
            },
            False,
        ),
    ),
)
def test_ranked_42nd(context, result):
    assert resolvers.ranked_42nd(context) is result


@pytest.mark.parametrize(
    "context, result",
    (
        (
            {
                "current": {
                    "is_last_series": True,
                    "series": s1,
                    "participant": {
                        "series": {
                            s1: {"score": 10, "max_score": 20, "rank": 35},
                        },
                    },
                },
            },
            True,
        ),
        (
            {
                "current": {
                    "is_last_series": True,
                    "series": s1,
                    "participant": {
                        "series": {
                            s1: {"score": 10, "max_score": 20, "rank": 15},
                        },
                    },
                },
            },
            True,
        ),
        (
            {
                "current": {
                    "is_last_series": False,
                    "series": s1,
                    "participant": {
                        "series": {
                            s1: {"score": 20, "max_score": 20, "rank": 15},
                        },
                    },
                },
            },
            False,
        ),
    ),
)
def test_successful_solver(context, result):
    assert resolvers.successfull_solver(context) is result


@pytest.mark.parametrize(
    "context, result",
    (
        (
            {
                "current": {
                    "is_last_series": True,
                    "series": s1,
                    "participant": {
                        "submissions": {"by_series": {s1: (sub1, sub2)}},
                    },
                },
            },
            True,
        ),
        (
            {
                "current": {
                    "is_last_series": True,
                    "series": s1,
                    "participant": {
                        "submissions": {"by_series": {s1: ()}},
                    },
                },
            },
            False,
        ),
        (
            {
                "current": {
                    "is_last_series": False,
                    "series": s1,
                    "participant": {
                        "submissions": {"by_series": {s1: (sub1, sub2)}},
                    },
                },
            },
            False,
        ),
    ),
)
def test_submitted_solution_in_last_series(context, result):
    assert resolvers.submitted_solution_in_last_series(context) is result


@pytest.mark.parametrize(
    "context, result",
    (
        (
            {
                "current": {
                    "series": s1,
                    "participant": {
                        "series": {
                            s1: {"rank": 6},
                        },
                    },
                },
            },
            True,
        ),
        (
            {
                "current": {
                    "series": s1,
                    "participant": {
                        "series": {
                            s1: {"rank": 7},
                        },
                    },
                },
            },
            False,
        ),
    ),
)
def test_fellowship_of_benzenes(context, result):
    assert resolvers.fellowship_of_benzenes(context) is result


@pytest.mark.parametrize(
    "context, result",
    (
        (
            {
                "participant": p1,
                "current": {
                    "is_last_series": True,
                },
                "by_grades": {
                    0: {
                        "tasks": {
                            s1: (t1, t2),
                        },
                        "by_participant": {p1: {"submissions": {"all": (t1, t2)}}},
                    },
                    1: {
                        "tasks": {
                            s2: (t3, t4),
                        },
                        "by_participant": {p1: {"submissions": {"all": (t3, t4)}}},
                    },
                },
            },
            True,
        ),
        # Not all tasks in last series
        (
            {
                "participant": p1,
                "current": {
                    "is_last_series": True,
                },
                "by_grades": {
                    0: {
                        "tasks": {
                            s1: (t1, t2),
                        },
                        "by_participant": {p1: {"submissions": {"all": (t1, t2)}}},
                    },
                    1: {
                        "tasks": {
                            s1: (t3, t4),
                        },
                        "by_participant": {p1: {"submissions": {"all": (t3,)}}},
                    },
                },
            },
            False,
        ),
        (
            {
                "participant": p1,
                "current": {
                    "is_last_series": True,
                },
                "by_grades": {
                    0: {
                        "tasks": {
                            s1: (t1, t2),
                        },
                        "by_participant": {p1: {"submissions": {"all": (t1, t2)}}},
                    },
                    1: {
                        "tasks": {
                            s1: (t3,),
                            s2: (t4,),
                        },
                        "by_participant": {p1: {"submissions": {"all": (t3,)}}},
                    },
                },
            },
            False,
        ),
        # Not enough grades
        (
            {
                "participant": p1,
                "current": {
                    "is_last_series": True,
                },
                "by_grades": {
                    0: {
                        "tasks": {
                            s1: (t1, t2),
                        },
                        "by_participant": {p1: {"submissions": {"all": (t1, t2)}}},
                    },
                },
            },
            False,
        ),
    ),
)
def test_submitted_solution_in_each_task_of_last_two_grades(context, result):
    assert (
        resolvers.submitted_solution_in_each_task_of_last_two_grades(context) is result
    )
